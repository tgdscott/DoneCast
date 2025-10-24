import React, { useEffect, useMemo, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Separator } from "@/components/ui/separator";
import { makeApi } from "@/lib/apiClient";
import { useToast } from "@/hooks/use-toast";
import {
  defaultLandingContent,
  normalizeLandingContent,
  prepareLandingPayload,
} from "@/lib/landingDefaults";
import { useResolvedTimezone } from "@/hooks/useResolvedTimezone";
import { formatInTimezone } from "@/lib/timezone";
import { Users, HelpCircle } from "lucide-react";
// FORCE UPDATE

const emptyReview = () => ({ quote: "", author: "", role: "", avatar_url: "", rating: 5 });
const emptyFaq = () => ({ question: "", answer: "" });

export default function AdminLandingEditor({ token }) {
  const { toast } = useToast();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [content, setContent] = useState(defaultLandingContent);
  const [initialContent, setInitialContent] = useState(defaultLandingContent);
  const [error, setError] = useState(null);
  const resolvedTimezone = useResolvedTimezone();

  useEffect(() => {
    if (!token) {
      setLoading(false);
      return;
    }
    let cancelled = false;
    const api = makeApi(token);
    setLoading(true);
    setError(null);
    api
      .get("/api/admin/landing")
      .then((data) => {
        if (cancelled) return;
        const normalized = normalizeLandingContent(data || {});
        setContent(normalized);
        setInitialContent(normalized);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err?.detail || err?.message || "Failed to load landing page content");
        setContent(defaultLandingContent);
        setInitialContent(defaultLandingContent);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [token]);

  const isDirty = useMemo(() => {
    return JSON.stringify(content) !== JSON.stringify(initialContent);
  }, [content, initialContent]);

  const lastSaved = useMemo(() => {
    if (!initialContent?.updated_at) return null;
    try {
      return new Date(initialContent.updated_at);
    } catch (err) {
      return null;
    }
  }, [initialContent?.updated_at]);
  const lastSavedDisplay = lastSaved
    ? formatInTimezone(lastSaved, { dateStyle: 'medium', timeStyle: 'short', timeZoneName: 'short' }, resolvedTimezone)
    : null;

  const updateField = (field, value) => {
    setContent((prev) => ({ ...prev, [field]: value }));
  };

  const updateReview = (index, field, value) => {
    setContent((prev) => {
      const next = prev.reviews.slice();
      next[index] = { ...next[index], [field]: value };
      return { ...prev, reviews: next };
    });
  };

  const updateFaq = (index, field, value) => {
    setContent((prev) => {
      const next = prev.faqs.slice();
      next[index] = { ...next[index], [field]: value };
      return { ...prev, faqs: next };
    });
  };

  const addReview = () => {
    setContent((prev) => ({ ...prev, reviews: [...prev.reviews, emptyReview()] }));
  };

  const removeReview = (index) => {
    setContent((prev) => ({
      ...prev,
      reviews: prev.reviews.filter((_, i) => i !== index),
    }));
  };

  const addFaq = () => {
    setContent((prev) => ({ ...prev, faqs: [...prev.faqs, emptyFaq()] }));
  };

  const removeFaq = (index) => {
    setContent((prev) => ({
      ...prev,
      faqs: prev.faqs.filter((_, i) => i !== index),
    }));
  };

  const handleResetToSaved = () => {
    setContent(initialContent);
  };

  const handleResetToDefaults = () => {
    setContent(defaultLandingContent);
  };

  const handleSave = async () => {
    if (!token) return;
    setSaving(true);
    setError(null);
    try {
      const api = makeApi(token);
      const payload = prepareLandingPayload(content);
      const data = await api.put("/api/admin/landing", payload);
      const normalized = normalizeLandingContent(data || {});
      setContent(normalized);
      setInitialContent(normalized);
      toast({ title: "Landing page updated", description: "Your changes were saved successfully and are now live on podcastplusplus.com" });
    } catch (err) {
      const message = err?.detail || err?.message || "Failed to save landing page content";
      setError(message);
      toast({ title: "Save failed", description: message, variant: "destructive" });
    } finally {
      setSaving(false);
    }
  };

  const disabled = loading || saving;

  return (
    <div className="space-y-6">
      {/* Important Notice Card */}
      <Card className="border-l-4 border-l-blue-500 bg-blue-50">
        <CardContent className="pt-6">
          <h3 className="font-semibold text-blue-900 mb-2">📝 What You Can Edit</h3>
          <p className="text-sm text-blue-800 mb-3">
            This page lets you edit the <strong>testimonials/reviews</strong> and <strong>FAQ section</strong> that appear near the bottom 
            of the front page at <strong>podcastplusplus.com</strong>. Changes take effect immediately when you save.
          </p>
          <h4 className="font-semibold text-blue-900 mb-2 mt-4">🔒 What You Can't Edit Here</h4>
          <p className="text-sm text-blue-800">
            The following sections are <strong>hardcoded in the source code</strong> and require developer changes to modify:
          </p>
          <ul className="text-sm text-blue-800 list-disc list-inside mt-2 space-y-1">
            <li>Hero title ("Professional Podcasting For Everyone")</li>
            <li>"Faster, Cheaper, Easier" pillars section</li>
            <li>Feature cards (Unlimited Hosting, AI-Powered Editing, etc.)</li>
            <li>Navigation menu and footer links</li>
            <li>"Why Choose Us" differentiators</li>
            <li>Step-by-step workflow section</li>
          </ul>
          <p className="text-sm text-blue-700 mt-3 italic font-medium">
            💡 To change hardcoded sections, ask the developer to update <code className="bg-blue-100 px-1 rounded font-mono">NewLanding.jsx</code>
          </p>
        </CardContent>
      </Card>

      <Card className="border-0 shadow-sm">
        <CardHeader className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
          <div>
            <CardTitle className="text-2xl" style={{ color: "#2C3E50" }}>
              Editable Front Page Content
            </CardTitle>
            <p className="text-sm text-gray-600">
              Manage customer testimonials and frequently asked questions on the public landing page
            </p>
            {error && (
              <p className="text-sm text-red-600 mt-2" role="alert">
                {error}
              </p>
            )}
            {lastSavedDisplay && (
              <p className="text-xs text-gray-500 mt-2">📅 Last saved {lastSavedDisplay}</p>
            )}
          </div>
          <div className="flex flex-wrap gap-2">
            <Button
              type="button"
              variant="outline"
              disabled={disabled}
              onClick={handleResetToDefaults}
            >
              Reset to defaults
            </Button>
            <Button
              type="button"
              variant="outline"
              disabled={disabled || !isDirty}
              onClick={handleResetToSaved}
            >
              Discard changes
            </Button>
            <Button type="button" onClick={handleSave} disabled={disabled || !isDirty}>
              {saving ? "Saving…" : "💾 Save changes"}
            </Button>
          </div>
        </CardHeader>
        <CardContent className="space-y-8">
          {/* Testimonials/Reviews Section */}
          <div className="space-y-4">
            <div className="pb-4 border-b">
              <h3 className="text-lg font-semibold text-gray-900 flex items-center gap-2">
                <Users size={20} className="text-primary" />
                Customer Testimonials
              </h3>
              <p className="text-sm text-gray-600 mt-1">
                These testimonials appear in the "What Our Users Say" section on the landing page.
              </p>
            </div>
            
            <div className="grid md:grid-cols-2 gap-4">
              <div>
                <Label htmlFor="reviews-heading">Section Heading</Label>
                <Input
                  id="reviews-heading"
                  value={content.reviews_heading}
                  onChange={(e) => updateField("reviews_heading", e.target.value)}
                  disabled={disabled}
                  placeholder="e.g., What Our Users Say"
                />
              </div>
              <div>
                <Label htmlFor="reviews-summary">Rating Summary</Label>
                <Input
                  id="reviews-summary"
                  value={content.reviews_summary}
                  onChange={(e) => updateField("reviews_summary", e.target.value)}
                  disabled={disabled}
                  placeholder="e.g., 4.9/5 from 2,847 reviews"
                />
              </div>
            </div>

            <Separator />

            <div className="space-y-4">
              {content.reviews.map((review, index) => (
                <Card key={index} className="border border-gray-200 bg-gray-50">
                  <CardContent className="space-y-4 pt-6">
                    <div className="flex items-center justify-between">
                      <h4 className="font-semibold text-base">Testimonial #{index + 1}</h4>
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        className="text-red-600 hover:text-red-700 hover:bg-red-50"
                        onClick={() => removeReview(index)}
                        disabled={disabled || content.reviews.length <= 1}
                      >
                        Remove
                      </Button>
                    </div>
                    <div>
                      <Label htmlFor={`review-quote-${index}`}>Customer Quote *</Label>
                      <Textarea
                        id={`review-quote-${index}`}
                        value={review.quote}
                        onChange={(e) => updateReview(index, "quote", e.target.value)}
                        disabled={disabled}
                        rows={3}
                        placeholder="What did this customer say about your product?"
                      />
                    </div>
                    <div className="grid md:grid-cols-2 gap-4">
                      <div>
                        <Label htmlFor={`review-author-${index}`}>Customer Name *</Label>
                        <Input
                          id={`review-author-${index}`}
                          value={review.author}
                          onChange={(e) => updateReview(index, "author", e.target.value)}
                          disabled={disabled}
                          placeholder="e.g., Sarah Johnson"
                        />
                      </div>
                      <div>
                        <Label htmlFor={`review-role-${index}`}>Role / Context</Label>
                        <Input
                          id={`review-role-${index}`}
                          value={review.role}
                          onChange={(e) => updateReview(index, "role", e.target.value)}
                          disabled={disabled}
                          placeholder="e.g., Podcast Host • 6 months"
                        />
                      </div>
                    </div>
                    <div className="grid md:grid-cols-2 gap-4">
                      <div>
                        <Label htmlFor={`review-avatar-${index}`}>Avatar URL (optional)</Label>
                        <Input
                          id={`review-avatar-${index}`}
                          value={review.avatar_url}
                          onChange={(e) => updateReview(index, "avatar_url", e.target.value)}
                          disabled={disabled}
                          placeholder="https://example.com/photo.jpg"
                        />
                        <p className="text-xs text-gray-500 mt-1">Leave blank to show initials instead</p>
                      </div>
                      <div>
                        <Label htmlFor={`review-rating-${index}`}>Star Rating (0-5)</Label>
                        <Input
                          id={`review-rating-${index}`}
                          type="number"
                          step="0.1"
                          min={0}
                          max={5}
                          value={review.rating ?? ""}
                          onChange={(e) => updateReview(index, "rating", e.target.value)}
                          disabled={disabled}
                          placeholder="5"
                        />
                      </div>
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>

            <Button type="button" variant="outline" onClick={addReview} disabled={disabled}>
              + Add Testimonial
            </Button>
          </div>

          <Separator className="my-8" />

          {/* FAQ Section */}
          <div className="space-y-4">
            <div className="pb-4 border-b">
              <h3 className="text-lg font-semibold text-gray-900 flex items-center gap-2">
                <HelpCircle size={20} className="text-secondary" />
                Frequently Asked Questions
              </h3>
              <p className="text-sm text-gray-600 mt-1">
                These questions and answers appear in an expandable FAQ section on the landing page.
              </p>
            </div>
            
            <div className="grid md:grid-cols-2 gap-4">
              <div>
                <Label htmlFor="faq-heading">Section Heading</Label>
                <Input
                  id="faq-heading"
                  value={content.faq_heading}
                  onChange={(e) => updateField("faq_heading", e.target.value)}
                  disabled={disabled}
                  placeholder="e.g., Frequently Asked Questions"
                />
              </div>
              <div>
                <Label htmlFor="faq-subheading">Section Subheading</Label>
                <Input
                  id="faq-subheading"
                  value={content.faq_subheading}
                  onChange={(e) => updateField("faq_subheading", e.target.value)}
                  disabled={disabled}
                  placeholder="e.g., Everything you need to know"
                />
              </div>
            </div>

            <Separator />

            <div className="space-y-4">
              {content.faqs.map((faq, index) => (
                <Card key={index} className="border border-gray-200 bg-gray-50">
                  <CardContent className="space-y-4 pt-6">
                    <div className="flex items-center justify-between">
                      <h4 className="font-semibold text-base">FAQ #{index + 1}</h4>
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        className="text-red-600 hover:text-red-700 hover:bg-red-50"
                        onClick={() => removeFaq(index)}
                        disabled={disabled || content.faqs.length <= 1}
                      >
                        Remove
                      </Button>
                    </div>
                    <div>
                      <Label htmlFor={`faq-question-${index}`}>Question *</Label>
                      <Input
                        id={`faq-question-${index}`}
                        value={faq.question}
                        onChange={(e) => updateFaq(index, "question", e.target.value)}
                        disabled={disabled}
                        placeholder="What question do users commonly ask?"
                      />
                    </div>
                    <div>
                      <Label htmlFor={`faq-answer-${index}`}>Answer *</Label>
                      <Textarea
                        id={`faq-answer-${index}`}
                        value={faq.answer}
                        onChange={(e) => updateFaq(index, "answer", e.target.value)}
                        disabled={disabled}
                        rows={3}
                        placeholder="Provide a clear, helpful answer..."
                      />
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>

            <Button type="button" variant="outline" onClick={addFaq} disabled={disabled}>
              + Add FAQ
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
