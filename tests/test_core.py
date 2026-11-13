import json
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from fastapi.testclient import TestClient
from core import Segment, group_words, padded_segments, gain_at, write_envelope, probe_media, render_video
from app import app

ROOT = Path(__file__).resolve().parents[1]
SAMPLES = ROOT / 'samples'


def test_scribe_filters_non_words_and_merges_short_pauses():
    words = [
        {'type': 'word', 'text': 'hello', 'start': 1, 'end': 1.3},
        {'type': 'spacing', 'text': ' ', 'start': 1.3, 'end': 1.9},
        {'type': 'word', 'text': 'world', 'start': 1.65, 'end': 2},
        {'type': 'audio_event', 'text': 'music', 'start': 2, 'end': 6},
        {'type': 'word', 'text': 'next', 'start': 4.2, 'end': 4.8},
    ]
    assert group_words(words, gap=0.5) == [Segment(1, 2), Segment(4.2, 4.8)]
    assert group_words(words, gap=2.3) == [Segment(1, 4.8)]


def test_overlap_pad_and_envelope():
    parts = padded_segments([Segment(1, 2), Segment(2.2, 3)], duration=10, pre=.15, post=.25)
    assert parts == [Segment(.85, 3.25)]
    low = 10 ** (-16 / 20)
    assert gain_at(-1, parts, low) == 1
    assert gain_at(1.5, parts, low) == pytest.approx(low)
    assert gain_at(5, parts, low) == 1
    with TemporaryDirectory() as tmp:
        p = Path(tmp) / 'env.wav'
        write_envelope(p, 2, [Segment(.5, 1)], reduction_db=16)
        assert p.is_file() and p.stat().st_size > 3000


def test_offline_sample_api_end_to_end():
    client = TestClient(app)
    response = client.post('/api/sample')
    assert response.status_code == 200, response.text
    job = response.json()['job_id']
    assert response.json()['has_music']
    timeline = client.get(f'/api/timeline/{job}?gap=1.0')
    assert timeline.status_code == 200, timeline.text
    assert len(timeline.json()['segments']) == 3
    result = client.post(f'/api/render/{job}', json={'gap': 1, 'reduction_db': 16, 'normal_music_db': -12})
    assert result.status_code == 200, result.text
    assert result.json()['has_original_audio']
    assert len(result.json()['speech_segments']) == 3
    video = client.get(f'/api/file/{job}/result')
    assert video.status_code == 200 and len(video.content) > 10000
    bad = client.post(f'/api/render/{job}', json={'manual_segments': [{'start': 20, 'end': 30}]})
    assert bad.status_code == 400
    security = client.get('/api/file/../../foo')
    assert security.status_code in (404, 422)


def test_upload_and_manual_segment_api():
    client = TestClient(app)
    with (SAMPLES / 'sample_video.mp4').open('rb') as f:
        resp = client.post('/api/video', files={'file': ('input.mp4', f, 'video/mp4')})
    assert resp.status_code == 200, resp.text
    job = resp.json()['job_id']
    assert not resp.json()['has_music']
    with (SAMPLES / 'sample_music.mp3').open('rb') as f:
        result = client.post(f'/api/music-upload/{job}', files={'file': ('song.mp3', f, 'audio/mpeg')})
    assert result.status_code == 200, result.text
    r = client.post(f'/api/render/{job}', json={'manual_segments': [{'start': 1, 'end': 3}]})
    assert r.status_code == 200, r.text
    assert r.json()['speech_segments'] == [{'start': 1.0, 'end': 3.0}]


def test_probe_sample():
    p = probe_media(SAMPLES / 'sample_video.mp4')
    assert p['duration'] == pytest.approx(15, abs=.01)
    assert p['has_audio'] and p['has_video']


def test_elevenlabs_request_contracts(monkeypatch, tmp_path):
    import httpx
    import elevenlabs_client as api
    monkeypatch.setenv('ELEVENLABS_API_KEY', 'demo-not-real')
    requested = []
    class MockClient:
        def __init__(self, *args, **kwargs):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def post(self, url, *, headers, data, files):
            requested.append((url, headers, data, files))
            if url.endswith('/video-to-music'):
                assert 'videos' in files
                assert data['model_id'] == 'music_v2_5'
                assert data['separate_tracks'] == 'false'
                return httpx.Response(200, content=b'ID3\x03\x00dummy', headers={'content-type': 'audio/mpeg'}, request=httpx.Request('POST', url))
            assert files.get('file')
            assert data['model_id'] == 'scribe_v2'
            assert data['timestamps_granularity'] == 'word'
            return httpx.Response(200, json={'text': 'Hello', 'words': [
                {'text': 'Hello', 'start': 0, 'end': .5, 'type': 'word'}
            ]}, request=httpx.Request('POST', url))
    monkeypatch.setattr(api.httpx, 'Client', MockClient)
    music = tmp_path / 'song.mp3'
    api.create_music(SAMPLES / 'sample_video.mp4', music, description='Cinematic', reference_audio=True)
    assert music.read_bytes() == b'ID3\x03\x00dummy'
    result = api.transcribe(SAMPLES / 'sample_video.mp4')
    assert result['words'][0]['start'] == 0
    assert len(requested) == 2


@pytest.mark.parametrize('reference_audio', [False, True])
def test_music_multipart_upload_matches_server_field(monkeypatch, tmp_path, reference_audio):
    from email.parser import BytesParser
    from email.policy import default
    import httpx
    import elevenlabs_client as api

    monkeypatch.setenv('ELEVENLABS_API_KEY', 'demo-not-real')
    video = tmp_path / 'clip.mp4'
    video.write_bytes(b'test-video-content')
    output = tmp_path / 'music.mp3'
    calls = []

    def receive(request):
        calls.append(request)
        message = BytesParser(policy=default).parsebytes(
            b'Content-Type: ' + request.headers['content-type'].encode()
            + b'\r\nMIME-Version: 1.0\r\n\r\n' + request.read())
        parts = {part.get_param('name', header='content-disposition'): part
                 for part in message.iter_parts()}
        # Match the actual server requirement after httpx encodes the multipart body.
        assert 'videos' in parts, 'Server requires a multipart file named videos'
        assert 'videos[]' not in parts
        assert parts['videos'].get_filename() == 'clip.mp4'
        assert parts['videos'].get_content_type() == 'video/mp4'
        assert parts['videos'].get_payload(decode=True) == video.read_bytes()
        assert parts['model_id'].get_payload(decode=True) == b'music_v2_5'
        assert parts['description'].get_payload(decode=True) == b'Cinematic'
        assert parts['use_audio_as_reference'].get_payload(decode=True) == (
            b'true' if reference_audio else b'false')
        return httpx.Response(200, content=b'ID3-test-music',
                              headers={'content-type': 'audio/mpeg'})

    real_client = httpx.Client
    monkeypatch.setattr(api.httpx, 'Client', lambda **kwargs: real_client(
        transport=httpx.MockTransport(receive), **kwargs))
    api.create_music(video, output, description=' Cinematic ', reference_audio=reference_audio)
    assert output.read_bytes() == b'ID3-test-music'
    assert len(calls) == 1


def test_fc_worker_contract_rejects_path_traversal(tmp_path):
    from fc_worker import execute
    with pytest.raises(ValueError, match='relative'):
        execute({'local_video': '../outside.mp4','local_music': 'music.mp3',
                 'local_output': 'out.mp4', 'speech_segments': []}, tmp_path)


def test_live_smoke_has_no_paid_calls_without_explicit_flag(monkeypatch):
    import sys
    from scripts import live_smoke
    monkeypatch.setenv('ELEVENLABS_API_KEY', 'demo-not-real')
    monkeypatch.setattr(live_smoke, 'check_access', lambda: (200, 'OK'))
    def must_not_be_called(*a, **kw):
        raise AssertionError('paid function must not be called')
    monkeypatch.setattr(live_smoke, 'run_paid', must_not_be_called)
    monkeypatch.setattr(sys, 'argv', ['live_smoke.py'])
    assert live_smoke.main() == 0


def test_live_smoke_auth_failure_stops_paid_requests(monkeypatch):
    import sys
    from scripts import live_smoke
    monkeypatch.setenv('ELEVENLABS_API_KEY', 'demo-not-real')
    monkeypatch.setattr(live_smoke, 'check_access', lambda: (401, 'Unauthorized'))
    def must_not_be_called(*a, **kw):
        raise AssertionError('paid function must not be called')
    monkeypatch.setattr(live_smoke, 'run_paid', must_not_be_called)
    monkeypatch.setattr(sys, 'argv', ['live_smoke.py', '--paid'])
    assert live_smoke.main() == 2
