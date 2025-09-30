import React, { useEffect, useMemo, useState } from "react";
import ReactQuill from "react-quill";
import "react-quill/dist/quill.snow.css";
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

const emptyReview = () => ({ quote: "", author: "", role: "", avatar_url: "", rating: 5 });
const emptyFaq = () => ({ question: "", answer: "" });

export default function AdminLandingEditor({ token }) {
  const { toast } = useToast();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [content, setContent] = useState(defaultLandingContent);
  const [initialContent, setInitialContent] = useState(defaultLandingContent);
  const [error, setError] = useState(null);

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
      toast({ title: "Landing page updated", description: "Your changes were saved successfully." });
    } catch (err) {
      const message = err?.detail || err?.message || "Failed to save landing page content";
      setError(message);
      toast({ title: "Save failed", description: message, variant: "destructive" });
    } finally {
      setSaving(false);
    }
  };

  const quillModules = useMemo(
    () => ({
      toolbar: [
        [{ header: [1, 2, 3, false] }],
        ["bold", "italic", "underline", "strike"],
        [{ list: "ordered" }, { list: "bullet" }],
        ["link", "blockquote"],
        ["clean"],
      ],
    }),
    []
  );

  const quillFormats = useMemo(
    () => [
      "header",
      "bold",
      "italic",
      "underline",
      "strike",
      "list",
      "bullet",
      "link",
      "blockquote",
    ],
    []
  );

  const disabled = loading || saving;

  return (
    <div className="space-y-6">
      <Card className="border-0 shadow-sm">
        <CardHeader className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
          <div>
            <CardTitle className="text-2xl" style={{ color: "#2C3E50" }}>
              Front Page Content
            </CardTitle>
            <p className="text-sm text-gray-600">
              Manage the reviews, FAQ entries, and hero messaging that appear on the public landing page.
            </p>
            {error && (
              <p className="text-sm text-red-600 mt-2" role="alert">
                {error}
              </p>
            )}
            {lastSaved && (
              <p className="text-xs text-gray-500 mt-2">Last saved {lastSaved.toLocaleString()}</p>
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
              {saving ? "Saving…" : "Save changes"}
            </Button>
          </div>
        </CardHeader>
        <CardContent className="space-y-6">
          <div className="space-y-2">
            <Label htmlFor="landing-hero-html">Hero Rich Text</Label>
            <ReactQuill
              id="landing-hero-html"
              theme="snow"
              value={content.hero_html}
              onChange={(value) => updateField("hero_html", value)}
              modules={quillModules}
              formats={quillFormats}
              readOnly={disabled}
            />
            <p className="text-xs text-gray-500">
              This content appears under the hero headline on the front page. Basic formatting, links, and lists are supported.
            </p>
          </div>
        </CardContent>
      </Card>

      <Card className="border-0 shadow-sm">
        <CardHeader>
          <CardTitle className="text-xl" style={{ color: "#2C3E50" }}>
            Reviews Section
          </CardTitle>
          <p className="text-sm text-gray-600">
            Update testimonials shown in the “Reviews” area. Leave avatar blank to use initials.
          </p>
        </CardHeader>
        <CardContent className="space-y-6">
          <div className="grid md:grid-cols-2 gap-4">
            <div>
              <Label htmlFor="reviews-heading">Heading</Label>
              <Input
                id="reviews-heading"
                value={content.reviews_heading}
                onChange={(e) => updateField("reviews_heading", e.target.value)}
                disabled={disabled}
              />
            </div>
            <div>
              <Label htmlFor="reviews-summary">Summary</Label>
              <Input
                id="reviews-summary"
                value={content.reviews_summary}
                onChange={(e) => updateField("reviews_summary", e.target.value)}
                disabled={disabled}
              />
            </div>
          </div>

          <Separator />

          <div className="space-y-6">
            {content.reviews.map((review, index) => (
              <Card key={index} className="border border-gray-200">
                <CardContent className="space-y-4 pt-6">
                  <div className="flex items-center justify-between">
                    <h3 className="font-semibold">Review #{index + 1}</h3>
                    <Button
                      type="button"
                      variant="ghost"
                      className="text-red-600 hover:text-red-700"
                      onClick={() => removeReview(index)}
                      disabled={disabled || content.reviews.length <= 1}
                    >
                      Remove
                    </Button>
                  </div>
                  <div>
                    <Label htmlFor={`review-quote-${index}`}>Quote</Label>
                    <Textarea
                      id={`review-quote-${index}`}
                      value={review.quote}
                      onChange={(e) => updateReview(index, "quote", e.target.value)}
                      disabled={disabled}
                      rows={3}
                    />
                  </div>
                  <div className="grid md:grid-cols-2 gap-4">
                    <div>
                      <Label htmlFor={`review-author-${index}`}>Author</Label>
                      <Input
                        id={`review-author-${index}`}
                        value={review.author}
                        onChange={(e) => updateReview(index, "author", e.target.value)}
                        disabled={disabled}
                      />
                    </div>
                    <div>
                      <Label htmlFor={`review-role-${index}`}>Role / context</Label>
                      <Input
                        id={`review-role-${index}`}
                        value={review.role}
                        onChange={(e) => updateReview(index, "role", e.target.value)}
                        disabled={disabled}
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
                        placeholder="https://..."
                      />
                    </div>
                    <div>
                      <Label htmlFor={`review-rating-${index}`}>Rating (0-5)</Label>
                      <Input
                        id={`review-rating-${index}`}
                        type="number"
                        step="0.1"
                        min={0}
                        max={5}
                        value={review.rating ?? ""}
                        onChange={(e) => updateReview(index, "rating", e.target.value)}
                        disabled={disabled}
                      />
                    </div>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>

          <Button type="button" variant="outline" onClick={addReview} disabled={disabled}>
            Add review
          </Button>
        </CardContent>
      </Card>

      <Card className="border-0 shadow-sm">
        <CardHeader>
          <CardTitle className="text-xl" style={{ color: "#2C3E50" }}>
            FAQ Section
          </CardTitle>
          <p className="text-sm text-gray-600">
            Control the questions and answers that appear in the FAQ panel.
          </p>
        </CardHeader>
        <CardContent className="space-y-6">
          <div className="grid md:grid-cols-2 gap-4">
            <div>
              <Label htmlFor="faq-heading">Heading</Label>
              <Input
                id="faq-heading"
                value={content.faq_heading}
                onChange={(e) => updateField("faq_heading", e.target.value)}
                disabled={disabled}
              />
            </div>
            <div>
              <Label htmlFor="faq-subheading">Subheading</Label>
              <Input
                id="faq-subheading"
                value={content.faq_subheading}
                onChange={(e) => updateField("faq_subheading", e.target.value)}
                disabled={disabled}
              />
            </div>
          </div>

          <Separator />

          <div className="space-y-6">
            {content.faqs.map((faq, index) => (
              <Card key={index} className="border border-gray-200">
                <CardContent className="space-y-4 pt-6">
                  <div className="flex items-center justify-between">
                    <h3 className="font-semibold">FAQ #{index + 1}</h3>
                    <Button
                      type="button"
                      variant="ghost"
                      className="text-red-600 hover:text-red-700"
                      onClick={() => removeFaq(index)}
                      disabled={disabled || content.faqs.length <= 1}
                    >
                      Remove
                    </Button>
                  </div>
                  <div>
                    <Label htmlFor={`faq-question-${index}`}>Question</Label>
                    <Input
                      id={`faq-question-${index}`}
                      value={faq.question}
                      onChange={(e) => updateFaq(index, "question", e.target.value)}
                      disabled={disabled}
                    />
                  </div>
                  <div>
                    <Label htmlFor={`faq-answer-${index}`}>Answer</Label>
                    <Textarea
                      id={`faq-answer-${index}`}
                      value={faq.answer}
                      onChange={(e) => updateFaq(index, "answer", e.target.value)}
                      disabled={disabled}
                      rows={3}
                    />
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>

          <Button type="button" variant="outline" onClick={addFaq} disabled={disabled}>
            Add FAQ
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
