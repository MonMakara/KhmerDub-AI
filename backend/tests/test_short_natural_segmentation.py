"""Occurrence-level coverage, natural boundaries and source-time compatibility."""
from dataclasses import replace

import pytest

from app.services.transcription.base import (
    TranscriptionSegment, WordTiming, identify_source_words,
)
from app.services.transcription.segmentation import (
    segment_transcript, validate_word_coverage, split_segment_at_word,
)
from app.services.dubbing.grouper import DubbingGrouper
from app.services.subtitles.generator import SubtitleCue, generate_srt


def source(tokens, step=0.42):
    words = [WordTiming(' '+word, index*step+0.000123, (index+1)*step-0.000234)
             for index, word in enumerate(tokens)]
    return identify_source_words([TranscriptionSegment(
        1, words[0].start, words[-1].end, ' '.join(tokens), words=words,
    )], 'real-source-digest', '/original/audio.wav')


@pytest.mark.parametrize('mode', ['original', 'sentence', 'dubbing'])
def test_ids_preserve_repeated_words_order_and_exact_intervals(mode):
    raw = source(['Practice']*20+['makes','progress.'])
    before = [w.to_dict() for s in raw for w in s.words]
    output = segment_transcript(raw, mode=mode)
    assert validate_word_coverage(raw, output)['source_words'] == 22
    assert [w.to_dict() for s in output for w in s.words] == before
    assert len({w.word_id for s in output for w in s.words}) == 22
    assert [s.id for s in segment_transcript(raw,mode=mode)] == [s.id for s in output]
    for segment in output:
        if mode != 'original':
            assert segment.start_time == segment.words[0].start
            assert segment.end_time == segment.words[-1].end
        assert segment.source_audio_reference == '/original/audio.wav'
    assert [w.to_dict() for s in raw for w in s.words] == before


def test_coverage_rejects_duplicate_occurrences_even_when_text_is_identical():
    raw = source(['go','go','go.'])
    output = segment_transcript(raw)
    output[0].words[1] = output[0].words[0]
    with pytest.raises(ValueError, match='coverage'):
        validate_word_coverage(raw,output)


def test_number_unit_technical_expression_and_cube_algorithm_are_kept_whole():
    tokens = ['Practice','the',"Rubik's",'Cube','for','30','seconds','using','the',
              'three','move','insert','then','perform','R','U',"R'","U'",'carefully.']
    raw = source(tokens, step=0.5)
    result = segment_transcript(raw)
    owner = {w.word.strip():s.id for s in result for w in s.words}
    for expression in [("Rubik's",'Cube'),('30','seconds'),('three','move','insert'),('R','U',"R'","U'")]:
        assert len({owner[word] for word in expression}) == 1
    assert validate_word_coverage(raw,result)['assigned_words'] == len(tokens)
    assert result[-1].words[-1].word.strip() == 'carefully.'


def test_unrelated_short_sentences_keep_their_gaps_and_punctuation():
    raw = [TranscriptionSegment(1,0,2,'Stop. Keep learning.',words=[
        WordTiming('Stop.',0,0.4),WordTiming(' Keep',1.1,1.4),WordTiming(' learning.',1.4,2)])]
    result=segment_transcript(raw,mode='dubbing')
    assert [s.text for s in result] == ['Stop.','Keep learning.']
    assert result[0].end_time == 0.4 and result[1].start_time == 1.1


def test_no_proportional_times_and_no_manual_split_without_alignment():
    raw=TranscriptionSegment(1,2,12,'One sentence. Another sentence.')
    result=segment_transcript([raw])
    assert len(result)==1
    assert result[0].is_approximate and result[0].words is None
    assert (result[0].start_time,result[0].end_time)==(2,12)
    with pytest.raises(ValueError,match='alignment'):
        split_segment_at_word(result[0],1)


def test_long_sentence_split_keeps_possessive_and_final_word():
    raw=source(['He','kept','working','toward','his','important','dreams','and','continued',
                'practicing','with','his','friends','every','single','day.'],step=0.6)
    result=segment_transcript(raw)
    assert len(result)>1
    assert all(s.end_time-s.start_time<=5 for s in result)
    assert all(s.words[-1].word.strip().lower() not in {'his','and','with','toward'} for s in result)
    assert result[-1].text.endswith('day.')


def test_subtitle_times_and_tts_group_mapping_preserve_source_content():
    raw=source(['Keep','learning,','keep','trying,','and','never','give','up.'],step=0.8)
    segments=segment_transcript(raw)
    cues=[SubtitleCue(s.segment_order,s.start_time,s.end_time,s.text) for s in segments]
    srt=generate_srt(cues)
    assert all(s.text in srt for s in segments)
    units=DubbingGrouper().group_segments(segments)
    assert [identifier for unit in units for identifier in unit.source_segment_ids] == [s.id for s in segments]
    assert ' '.join(unit.combined_english_text for unit in units) == ' '.join(s.text for s in segments)
    assert segments[0].start_time == raw[0].words[0].start


def test_resegmentation_retains_approved_text_and_never_retargets_by_order(client, db_session):
    import json
    from app.models.project import Project, TranscriptSegment, TranslationSegment, GeneratedAudio

    raw=source(['This','is','the','first','part','of','a','long','sentence','and','this','is','the','ending.'],step=0.65)
    project=Project(title='Protect approved mappings',raw_transcript_json=json.dumps([s.to_dict() for s in raw]))
    db_session.add(project);db_session.flush()
    old=TranscriptSegment(project_id=project.id,segment_order=1,start_time=raw[0].start_time,end_time=raw[0].end_time,text=raw[0].text)
    db_session.add(old);db_session.flush()
    approved=TranslationSegment(project_id=project.id,transcript_segment_id=old.id,segment_order=1,source_text=old.text,khmer_text='អត្ថបទដែលបានអនុម័ត',is_manually_edited=True)
    excess=TranslationSegment(project_id=project.id,segment_order=99,source_text='A preserved earlier phrase.',khmer_text='រក្សាទុក',is_manually_edited=True)
    db_session.add_all([approved,excess]);db_session.flush()
    audio=GeneratedAudio(project_id=project.id,translation_segment_id=approved.id,audio_path='/original/keep.wav',duration_seconds=8)
    db_session.add(audio);db_session.commit()
    previous=approved.source_text
    response=client.post(f'/api/projects/{project.id}/transcript/segmentation/apply',json={'mode':'sentence','confirm':True})
    assert response.status_code==200
    db_session.refresh(approved);db_session.refresh(excess);db_session.refresh(audio)
    assert approved.khmer_text=='អត្ថបទដែលបានអនុម័ត'
    assert approved.source_text==previous
    assert approved.transcript_segment_id is None
    assert approved.is_outdated and audio.is_outdated
    assert excess.khmer_text=='រក្សាទុក' and excess.is_outdated
    assert db_session.query(TranslationSegment).filter_by(project_id=project.id).count()==2
    identifiers=[s['id'] for s in response.json()['segments']]
    repeated=client.post(f'/api/projects/{project.id}/transcript/segmentation/apply',json={'mode':'sentence','confirm':True})
    assert repeated.status_code==200
    assert [s['id'] for s in repeated.json()['segments']]==identifiers


def test_edited_text_is_not_silently_replaced_by_old_word_alignment():
    raw=source(['Original','aligned','words.'])[0]
    edited=replace(raw,text='New human correction.',is_manually_edited=True)
    with pytest.raises(ValueError,match='realignment'):
        split_segment_at_word(edited,1)


def test_pause_does_not_orphan_the_last_word_of_a_clause():
    raw=[TranscriptionSegment(1,0,3.4,'Six months passed, nothing.',words=[
        WordTiming('Six',0,0.3),WordTiming(' months',0.3,0.8),
        WordTiming(' passed,',0.8,1.6),WordTiming(' nothing.',2.3,2.6)])]
    result=segment_transcript(raw,mode='dubbing')
    assert len(result)==1
    assert result[0].text=='Six months passed, nothing.'
