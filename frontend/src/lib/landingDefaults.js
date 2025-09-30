export const defaultLandingContent = {
  hero_html:
    "<p>Join thousands of creators who've discovered the joy of effortless podcasting. <strong>Average setup time: Under 5 minutes.</strong></p>",
  reviews_heading: "Real Stories from Real Podcasters",
  reviews_summary: "4.9/5 from 2,847 reviews",
  reviews: [
    {
      quote:
        "I was terrified of the technical side of podcasting. Podcast Plus Plus made it so simple that I launched my first episode in under 30 minutes! Now I have 50+ episodes and growing.",
      author: "Sarah Johnson",
      role: "Wellness Coach • 12 months on Plus Plus",
      avatar_url: "https://placehold.co/60x60/E2E8F0/A0AEC0?text=SJ",
      rating: 5,
    },
    {
      quote:
        "My podcast now reaches 10,000+ listeners monthly. The automatic distribution to all platforms was a game-changer for my reach!",
      author: "Maria Rodriguez",
      role: "Community Leader • 8 months on Plus Plus",
      avatar_url: "https://placehold.co/60x60/E2E8F0/A0AEC0?text=MR",
      rating: 5,
    },
    {
      quote:
        "The AI editing tools are unbelievable. I cut my production time by 80% and the quality actually went up.",
      author: "Dev Patel",
      role: "Startup Founder • 6 months on Plus Plus",
      avatar_url: "https://placehold.co/60x60/E2E8F0/A0AEC0?text=DP",
      rating: 5,
    },
  ],
  faq_heading: "Frequently Asked Questions",
  faq_subheading: "Everything you need to know about getting started with Podcast Plus Plus",
  faqs: [
    {
      question: "Do I need any technical experience to use Podcast Plus Plus?",
      answer:
        "Absolutely not! Plus Plus is designed for complete beginners. If you can use email, you can create professional podcasts with our platform.",
    },
    {
      question: "How long does it take to publish my first episode?",
      answer:
        "Most users publish their first episode within 30 minutes of signing up. Our average setup time is under 5 minutes, and episode creation takes just a few more minutes.",
    },
    {
      question: "What platforms will my podcast be available on?",
      answer:
        "Your podcast will automatically be distributed to 20+ major platforms including Spotify, Apple Podcasts, Google Podcasts, and many more with just one click.",
    },
    {
      question: "Is there really a free trial with no credit card required?",
      answer:
        "Yes! You get full access to all features for 14 days completely free. No credit card required, no hidden fees, and you can cancel anytime.",
    },
    {
      question: "What if I'm not satisfied with the service?",
      answer:
        "We offer a 30-day money-back guarantee. If you're not completely satisfied, we'll refund your payment, no questions asked.",
    },
  ],
  updated_at: null,
};

const clampRating = (value) => {
  if (value === null || value === undefined || value === "") return null;
  const num = Number(value);
  if (!Number.isFinite(num)) return null;
  if (num < 0) return 0;
  if (num > 5) return 5;
  return Number(num.toFixed(1));
};

const normalizeReview = (review) => {
  if (!review || typeof review !== "object") return null;
  const quote = (review.quote || "").trim();
  const author = (review.author || "").trim();
  const role = (review.role || "").trim();
  const avatar = (review.avatar_url || "").trim();
  const rating = clampRating(review.rating);
  if (!quote && !author) return null;
  return {
    quote,
    author,
    role,
    avatar_url: avatar,
    rating,
  };
};

const normalizeFaq = (faq) => {
  if (!faq || typeof faq !== "object") return null;
  const question = (faq.question || faq.q || "").trim();
  const answer = (faq.answer || faq.a || "").trim();
  if (!question && !answer) return null;
  return { question, answer };
};

export const normalizeLandingContent = (payload = {}) => {
  const base = { ...defaultLandingContent };
  const heroHtml = typeof payload.hero_html === "string" && payload.hero_html.trim().length
    ? payload.hero_html
    : base.hero_html;
  const reviewsHeading = typeof payload.reviews_heading === "string" && payload.reviews_heading.trim().length
    ? payload.reviews_heading
    : base.reviews_heading;
  const reviewsSummary = typeof payload.reviews_summary === "string" && payload.reviews_summary.trim().length
    ? payload.reviews_summary
    : base.reviews_summary;
  const faqHeading = typeof payload.faq_heading === "string" && payload.faq_heading.trim().length
    ? payload.faq_heading
    : base.faq_heading;
  const faqSubheading = typeof payload.faq_subheading === "string" && payload.faq_subheading.trim().length
    ? payload.faq_subheading
    : base.faq_subheading;

  const normalizedReviews = Array.isArray(payload.reviews)
    ? payload.reviews.map(normalizeReview).filter(Boolean)
    : [];
  const normalizedFaqs = Array.isArray(payload.faqs)
    ? payload.faqs.map(normalizeFaq).filter(Boolean)
    : [];

  return {
    hero_html: heroHtml,
    reviews_heading: reviewsHeading,
    reviews_summary: reviewsSummary,
    reviews: normalizedReviews.length ? normalizedReviews : base.reviews,
    faq_heading: faqHeading,
    faq_subheading: faqSubheading,
    faqs: normalizedFaqs.length ? normalizedFaqs : base.faqs,
    updated_at: payload.updated_at || null,
  };
};

export const prepareLandingPayload = (content = {}) => {
  const heroHtml = typeof content.hero_html === "string" ? content.hero_html : defaultLandingContent.hero_html;
  const reviewsHeading = typeof content.reviews_heading === "string" && content.reviews_heading.trim().length
    ? content.reviews_heading
    : defaultLandingContent.reviews_heading;
  const reviewsSummary = typeof content.reviews_summary === "string" && content.reviews_summary.trim().length
    ? content.reviews_summary
    : defaultLandingContent.reviews_summary;
  const faqHeading = typeof content.faq_heading === "string" && content.faq_heading.trim().length
    ? content.faq_heading
    : defaultLandingContent.faq_heading;
  const faqSubheading = typeof content.faq_subheading === "string" && content.faq_subheading.trim().length
    ? content.faq_subheading
    : defaultLandingContent.faq_subheading;

  const reviews = Array.isArray(content.reviews)
    ? content.reviews
        .map((review) => {
          if (!review || typeof review !== "object") return null;
          const quote = (review.quote || "").trim();
          const author = (review.author || "").trim();
          const role = (review.role || "").trim();
          const avatarUrl = (review.avatar_url || "").trim();
          const rating = clampRating(review.rating);
          if (!quote && !author && !role && !avatarUrl) {
            return null;
          }
          return {
            quote,
            author,
            role: role || null,
            avatar_url: avatarUrl || null,
            rating,
          };
        })
        .filter(Boolean)
    : [];

  const faqs = Array.isArray(content.faqs)
    ? content.faqs
        .map((faq) => {
          if (!faq || typeof faq !== "object") return null;
          const question = (faq.question || faq.q || "").trim();
          const answer = (faq.answer || faq.a || "").trim();
          if (!question && !answer) {
            return null;
          }
          return { question, answer };
        })
        .filter(Boolean)
    : [];

  return {
    hero_html: heroHtml,
    reviews_heading: reviewsHeading,
    reviews_summary: reviewsSummary,
    reviews,
    faq_heading: faqHeading,
    faq_subheading: faqSubheading,
    faqs,
  };
};
