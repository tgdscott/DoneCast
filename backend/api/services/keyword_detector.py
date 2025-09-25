from typing import List, Dict, Any, Set, Optional, Tuple
from thefuzz import fuzz

def find_keywords(word_timestamps: List[Dict[str, Any]], keywords: Set[str]) -> List[Dict[str, Any]]:
    """
    Finds occurrences of specific keywords in a word-level transcript.
    """
    found_keywords = []
    for i, word_data in enumerate(word_timestamps):
        word = word_data['word'].strip(".,!?").lower()
        if word in keywords:
            found_keywords.append({
                "keyword": word,
                "start_time_s": word_data['start'],
                "end_time_s": word_data['end'],
                "index": i
            })
    return found_keywords

def analyze_flubber_instance(
    word_timestamps: List[Dict[str, Any]],
    flubber_word_index: int,
    window_s: int = 15,
    similarity_threshold: int = 85
) -> Optional[Tuple[float, float]]:
    """
    Analyzes the text before and after a "flubber" keyword to find a repeated mistake.
    """
    flubber_event = word_timestamps[flubber_word_index]
    flubber_start_s = flubber_event['start']
    words_before = []
    for i in range(flubber_word_index - 1, -1, -1):
        word_data = word_timestamps[i]
        if flubber_start_s - word_data['start'] > window_s:
            break
        words_before.insert(0, word_data)
    if not words_before:
        return None
    text_before = " ".join([w['word'] for w in words_before])
    mistake_start_s = words_before[0]['start']
    words_after = []
    for i in range(flubber_word_index + 1, len(word_timestamps)):
        word_data = word_timestamps[i]
        if len(" ".join([w['word'] for w in words_after])) >= len(text_before):
            break
        words_after.append(word_data)
    if not words_after:
        return None
    text_after = " ".join([w['word'] for w in words_after])
    similarity = fuzz.ratio(text_before.lower(), text_after.lower())
    if similarity >= similarity_threshold:
        segment_to_remove = (mistake_start_s, flubber_event['end_time_s'])
        return segment_to_remove
    return None

def get_text_after_keyword(
    word_timestamps: List[Dict[str, Any]],
    keyword_event: Dict[str, Any],
    max_pause_s: float = 1.5
) -> str:
    """
    Extracts the string of text spoken after a keyword, stopping at a long pause.
    """
    command_words = []
    start_index = keyword_event['index'] + 1
    
    if start_index >= len(word_timestamps):
        return ""

    last_word_end_s = keyword_event['end_time_s']

    for i in range(start_index, len(word_timestamps)):
        word_data = word_timestamps[i]
        
        # Check for a long pause before this word
        pause_duration = word_data['start'] - last_word_end_s
        if pause_duration > max_pause_s:
            break
            
        command_words.append(word_data['word'])
        last_word_end_s = word_data['end']
    
    return " ".join(command_words)
