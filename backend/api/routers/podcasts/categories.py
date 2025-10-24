"""Apple Podcasts Categories endpoint.

Based on official Apple Podcasts categories:
https://podcasters.apple.com/support/1691-apple-podcasts-categories

Note: Frontend expects flat list with category_id field (legacy Spreaker format).
"""

from fastapi import APIRouter

router = APIRouter()

# Apple Podcasts Categories - flattened for frontend compatibility
# Format: {"category_id": "unique-id", "name": "Display Name"}
# Subcategories shown with › separator
APPLE_PODCAST_CATEGORIES_FLAT = [
    # Arts
    {"category_id": "arts", "name": "Arts"},
    {"category_id": "arts-books", "name": "Arts › Books"},
    {"category_id": "arts-design", "name": "Arts › Design"},
    {"category_id": "arts-fashion-beauty", "name": "Arts › Fashion & Beauty"},
    {"category_id": "arts-food", "name": "Arts › Food"},
    {"category_id": "arts-performing-arts", "name": "Arts › Performing Arts"},
    {"category_id": "arts-visual-arts", "name": "Arts › Visual Arts"},
    
    # Business
    {"category_id": "business", "name": "Business"},
    {"category_id": "business-careers", "name": "Business › Careers"},
    {"category_id": "business-entrepreneurship", "name": "Business › Entrepreneurship"},
    {"category_id": "business-investing", "name": "Business › Investing"},
    {"category_id": "business-management", "name": "Business › Management"},
    {"category_id": "business-marketing", "name": "Business › Marketing"},
    {"category_id": "business-non-profit", "name": "Business › Non-Profit"},
    
    # Comedy
    {"category_id": "comedy", "name": "Comedy"},
    {"category_id": "comedy-interviews", "name": "Comedy › Comedy Interviews"},
    {"category_id": "comedy-improv", "name": "Comedy › Improv"},
    {"category_id": "comedy-stand-up", "name": "Comedy › Stand-Up"},
    
    # Education
    {"category_id": "education", "name": "Education"},
    {"category_id": "education-courses", "name": "Education › Courses"},
    {"category_id": "education-how-to", "name": "Education › How To"},
    {"category_id": "education-language-learning", "name": "Education › Language Learning"},
    {"category_id": "education-self-improvement", "name": "Education › Self-Improvement"},
    
    # Fiction
    {"category_id": "fiction", "name": "Fiction"},
    {"category_id": "fiction-comedy-fiction", "name": "Fiction › Comedy Fiction"},
    {"category_id": "fiction-drama", "name": "Fiction › Drama"},
    {"category_id": "fiction-science-fiction", "name": "Fiction › Science Fiction"},
    
    # Government
    {"category_id": "government", "name": "Government"},
    
    # History
    {"category_id": "history", "name": "History"},
    
    # Health & Fitness
    {"category_id": "health-fitness", "name": "Health & Fitness"},
    {"category_id": "health-fitness-alternative-health", "name": "Health & Fitness › Alternative Health"},
    {"category_id": "health-fitness-fitness", "name": "Health & Fitness › Fitness"},
    {"category_id": "health-fitness-medicine", "name": "Health & Fitness › Medicine"},
    {"category_id": "health-fitness-mental-health", "name": "Health & Fitness › Mental Health"},
    {"category_id": "health-fitness-nutrition", "name": "Health & Fitness › Nutrition"},
    {"category_id": "health-fitness-sexuality", "name": "Health & Fitness › Sexuality"},
    
    # Kids & Family
    {"category_id": "kids-family", "name": "Kids & Family"},
    {"category_id": "kids-family-education-for-kids", "name": "Kids & Family › Education for Kids"},
    {"category_id": "kids-family-parenting", "name": "Kids & Family › Parenting"},
    {"category_id": "kids-family-pets-animals", "name": "Kids & Family › Pets & Animals"},
    {"category_id": "kids-family-stories-for-kids", "name": "Kids & Family › Stories for Kids"},
    
    # Leisure
    {"category_id": "leisure", "name": "Leisure"},
    {"category_id": "leisure-animation-manga", "name": "Leisure › Animation & Manga"},
    {"category_id": "leisure-automotive", "name": "Leisure › Automotive"},
    {"category_id": "leisure-aviation", "name": "Leisure › Aviation"},
    {"category_id": "leisure-crafts", "name": "Leisure › Crafts"},
    {"category_id": "leisure-games", "name": "Leisure › Games"},
    {"category_id": "leisure-hobbies", "name": "Leisure › Hobbies"},
    {"category_id": "leisure-home-garden", "name": "Leisure › Home & Garden"},
    {"category_id": "leisure-video-games", "name": "Leisure › Video Games"},
    
    # Music
    {"category_id": "music", "name": "Music"},
    {"category_id": "music-commentary", "name": "Music › Music Commentary"},
    {"category_id": "music-history", "name": "Music › Music History"},
    {"category_id": "music-interviews", "name": "Music › Music Interviews"},
    
    # News
    {"category_id": "news", "name": "News"},
    {"category_id": "news-business-news", "name": "News › Business News"},
    {"category_id": "news-daily-news", "name": "News › Daily News"},
    {"category_id": "news-entertainment-news", "name": "News › Entertainment News"},
    {"category_id": "news-news-commentary", "name": "News › News Commentary"},
    {"category_id": "news-politics", "name": "News › Politics"},
    {"category_id": "news-sports-news", "name": "News › Sports News"},
    {"category_id": "news-tech-news", "name": "News › Tech News"},
    
    # Religion & Spirituality
    {"category_id": "religion-spirituality", "name": "Religion & Spirituality"},
    {"category_id": "religion-spirituality-buddhism", "name": "Religion & Spirituality › Buddhism"},
    {"category_id": "religion-spirituality-christianity", "name": "Religion & Spirituality › Christianity"},
    {"category_id": "religion-spirituality-hinduism", "name": "Religion & Spirituality › Hinduism"},
    {"category_id": "religion-spirituality-islam", "name": "Religion & Spirituality › Islam"},
    {"category_id": "religion-spirituality-judaism", "name": "Religion & Spirituality › Judaism"},
    {"category_id": "religion-spirituality-religion", "name": "Religion & Spirituality › Religion"},
    {"category_id": "religion-spirituality-spirituality", "name": "Religion & Spirituality › Spirituality"},
    
    # Science
    {"category_id": "science", "name": "Science"},
    {"category_id": "science-astronomy", "name": "Science › Astronomy"},
    {"category_id": "science-chemistry", "name": "Science › Chemistry"},
    {"category_id": "science-earth-sciences", "name": "Science › Earth Sciences"},
    {"category_id": "science-life-sciences", "name": "Science › Life Sciences"},
    {"category_id": "science-mathematics", "name": "Science › Mathematics"},
    {"category_id": "science-natural-sciences", "name": "Science › Natural Sciences"},
    {"category_id": "science-nature", "name": "Science › Nature"},
    {"category_id": "science-physics", "name": "Science › Physics"},
    {"category_id": "science-social-sciences", "name": "Science › Social Sciences"},
    
    # Society & Culture
    {"category_id": "society-culture", "name": "Society & Culture"},
    {"category_id": "society-culture-documentary", "name": "Society & Culture › Documentary"},
    {"category_id": "society-culture-personal-journals", "name": "Society & Culture › Personal Journals"},
    {"category_id": "society-culture-philosophy", "name": "Society & Culture › Philosophy"},
    {"category_id": "society-culture-places-travel", "name": "Society & Culture › Places & Travel"},
    {"category_id": "society-culture-relationships", "name": "Society & Culture › Relationships"},
    
    # Sports
    {"category_id": "sports", "name": "Sports"},
    {"category_id": "sports-baseball", "name": "Sports › Baseball"},
    {"category_id": "sports-basketball", "name": "Sports › Basketball"},
    {"category_id": "sports-cricket", "name": "Sports › Cricket"},
    {"category_id": "sports-fantasy-sports", "name": "Sports › Fantasy Sports"},
    {"category_id": "sports-football", "name": "Sports › Football"},
    {"category_id": "sports-golf", "name": "Sports › Golf"},
    {"category_id": "sports-hockey", "name": "Sports › Hockey"},
    {"category_id": "sports-rugby", "name": "Sports › Rugby"},
    {"category_id": "sports-running", "name": "Sports › Running"},
    {"category_id": "sports-soccer", "name": "Sports › Soccer"},
    {"category_id": "sports-swimming", "name": "Sports › Swimming"},
    {"category_id": "sports-tennis", "name": "Sports › Tennis"},
    {"category_id": "sports-volleyball", "name": "Sports › Volleyball"},
    {"category_id": "sports-wilderness", "name": "Sports › Wilderness"},
    {"category_id": "sports-wrestling", "name": "Sports › Wrestling"},
    
    # Technology
    {"category_id": "technology", "name": "Technology"},
    
    # True Crime
    {"category_id": "true-crime", "name": "True Crime"},
    
    # TV & Film
    {"category_id": "tv-film", "name": "TV & Film"},
    {"category_id": "tv-film-after-shows", "name": "TV & Film › After Shows"},
    {"category_id": "tv-film-film-history", "name": "TV & Film › Film History"},
    {"category_id": "tv-film-film-interviews", "name": "TV & Film › Film Interviews"},
    {"category_id": "tv-film-film-reviews", "name": "TV & Film › Film Reviews"},
    {"category_id": "tv-film-tv-reviews", "name": "TV & Film › TV Reviews"},
]


@router.get("/categories")
def get_podcast_categories():
    """Get Apple Podcasts categories (no auth required)."""
    return {"categories": APPLE_PODCAST_CATEGORIES_FLAT}
