import React, { useEffect, useState } from 'react';
import { makeApi } from '@/lib/apiClient';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { ChevronDown, ChevronUp, Save, Loader2, AlertCircle, Info } from 'lucide-react';

export default function AdminLandingEditor({ token }) {
  const [content, setContent] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(false);
  
  // Collapsible section states
  const [expandedSections, setExpandedSections] = useState({
    hero: true,
    aiEditing: false,
    doneForYou: false,
    threeSteps: false,
    features: false,
    why: false,
    finalCta: false,
    reviews: false,
    faqs: false,
  });

  useEffect(() => {
    const api = makeApi(token);
    api
      .get('/api/admin/landing')
      .then((data) => {
        setContent(data);
        setLoading(false);
      })
      .catch((err) => {
        setError(err.message || 'Failed to load landing page content');
        setLoading(false);
      });
  }, [token]);

  const toggleSection = (section) => {
    setExpandedSections((prev) => ({ ...prev, [section]: !prev[section] }));
  };

  const handleSave = async () => {
    setSaving(true);
    setError(null);
    setSuccess(false);

    try {
      const api = makeApi(token);
      await api.put('/api/admin/landing', content);
      setSuccess(true);
      setTimeout(() => setSuccess(false), 3000);
    } catch (err) {
      setError(err.message || 'Failed to save changes');
    } finally {
      setSaving(false);
    }
  };

  const updateField = (path, value) => {
    setContent((prev) => {
      const updated = { ...prev };
      const keys = path.split('.');
      let current = updated;
      
      for (let i = 0; i < keys.length - 1; i++) {
        if (!current[keys[i]]) current[keys[i]] = {};
        current = current[keys[i]];
      }
      
      current[keys[keys.length - 1]] = value;
      return updated;
    });
  };

  const updateArrayItem = (path, index, field, value) => {
    setContent((prev) => {
      const updated = { ...prev };
      const keys = path.split('.');
      let current = updated;
      
      for (let i = 0; i < keys.length - 1; i++) {
        current = current[keys[i]];
      }
      
      const array = [...current[keys[keys.length - 1]]];
      array[index] = { ...array[index], [field]: value };
      current[keys[keys.length - 1]] = array;
      
      return updated;
    });
  };

  const addArrayItem = (path, template) => {
    setContent((prev) => {
      const updated = { ...prev };
      const keys = path.split('.');
      let current = updated;
      
      for (let i = 0; i < keys.length - 1; i++) {
        current = current[keys[i]];
      }
      
      const array = [...(current[keys[keys.length - 1]] || [])];
      array.push(template);
      current[keys[keys.length - 1]] = array;
      
      return updated;
    });
  };

  const removeArrayItem = (path, index) => {
    setContent((prev) => {
      const updated = { ...prev };
      const keys = path.split('.');
      let current = updated;
      
      for (let i = 0; i < keys.length - 1; i++) {
        current = current[keys[i]];
      }
      
      const array = [...current[keys[keys.length - 1]]];
      array.splice(index, 1);
      current[keys[keys.length - 1]] = array;
      
      return updated;
    });
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center p-12">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    );
  }

  if (!content) {
    return (
      <Alert variant="destructive">
        <AlertCircle className="h-4 w-4" />
        <AlertDescription>Failed to load landing page content</AlertDescription>
      </Alert>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header with save button */}
      <Card>
        <CardHeader>
          <CardTitle>Landing Page Editor</CardTitle>
          <CardDescription>
            Edit all sections of the public-facing landing page. Changes appear immediately after saving.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Alert>
            <Info className="h-4 w-4" />
            <AlertDescription>
              <strong>Important:</strong> Navigation, footer links, and page structure are hardcoded. 
              You can edit all text, bullet points, and testimonials/FAQs below.
            </AlertDescription>
          </Alert>
          
          <div className="mt-4 flex gap-2">
            <Button onClick={handleSave} disabled={saving}>
              {saving ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Saving...
                </>
              ) : (
                <>
                  <Save className="mr-2 h-4 w-4" />
                  Save All Changes
                </>
              )}
            </Button>
            
            {success && (
              <Alert className="py-2 border-green-500 bg-green-50">
                <AlertDescription className="text-green-700">
                  Changes saved successfully!
                </AlertDescription>
              </Alert>
            )}
            
            {error && (
              <Alert variant="destructive" className="py-2">
                <AlertDescription>{error}</AlertDescription>
              </Alert>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Hero Section */}
      <Card>
        <CardHeader 
          className="cursor-pointer hover:bg-muted/50" 
          onClick={() => toggleSection('hero')}
        >
          <div className="flex items-center justify-between">
            <div>
              <CardTitle>Hero Section (Top of Page)</CardTitle>
              <CardDescription>Main headline, description, and call-to-action</CardDescription>
            </div>
            {expandedSections.hero ? <ChevronUp /> : <ChevronDown />}
          </div>
        </CardHeader>
        {expandedSections.hero && (
          <CardContent className="space-y-4">
            <div>
              <label className="block text-sm font-medium mb-1">Label (above title)</label>
              <Input
                value={content.hero.label}
                onChange={(e) => updateField('hero.label', e.target.value)}
                placeholder="Patent-Pending AI Technology"
              />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">Main Title</label>
              <Input
                value={content.hero.title}
                onChange={(e) => updateField('hero.title', e.target.value)}
                placeholder="Professional Podcasting"
              />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">Title Highlight (red text)</label>
              <Input
                value={content.hero.title_highlight}
                onChange={(e) => updateField('hero.title_highlight', e.target.value)}
                placeholder="For Everyone"
              />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">Description</label>
              <Textarea
                value={content.hero.description}
                onChange={(e) => updateField('hero.description', e.target.value)}
                placeholder="No experience needed..."
                rows={3}
              />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">Call-to-Action Button Text</label>
              <Input
                value={content.hero.cta_text}
                onChange={(e) => updateField('hero.cta_text', e.target.value)}
                placeholder="Start Your Free Trial"
              />
            </div>
            <div>
              <label className="block text-sm font-medium mb-2">Meta Items (small text below CTA)</label>
              {content.hero.meta_items.map((item, idx) => (
                <div key={idx} className="flex gap-2 mb-2">
                  <Input
                    value={item}
                    onChange={(e) => {
                      const newItems = [...content.hero.meta_items];
                      newItems[idx] = e.target.value;
                      updateField('hero.meta_items', newItems);
                    }}
                    placeholder={`Meta item ${idx + 1}`}
                  />
                  <Button 
                    variant="outline" 
                    size="sm"
                    onClick={() => {
                      const newItems = content.hero.meta_items.filter((_, i) => i !== idx);
                      updateField('hero.meta_items', newItems);
                    }}
                  >
                    Remove
                  </Button>
                </div>
              ))}
              <Button
                variant="outline"
                size="sm"
                onClick={() => updateField('hero.meta_items', [...content.hero.meta_items, ''])}
              >
                Add Meta Item
              </Button>
            </div>
          </CardContent>
        )}
      </Card>

      {/* AI Editing Section */}
      <Card>
        <CardHeader 
          className="cursor-pointer hover:bg-muted/50" 
          onClick={() => toggleSection('aiEditing')}
        >
          <div className="flex items-center justify-between">
            <div>
              <CardTitle>AI Editing Section</CardTitle>
              <CardDescription>"Edit in Real-Time While You Record"</CardDescription>
            </div>
            {expandedSections.aiEditing ? <ChevronUp /> : <ChevronDown />}
          </div>
        </CardHeader>
        {expandedSections.aiEditing && (
          <CardContent className="space-y-4">
            <div>
              <label className="block text-sm font-medium mb-1">Pill Text</label>
              <Input
                value={content.ai_editing.pill_text}
                onChange={(e) => updateField('ai_editing.pill_text', e.target.value)}
                placeholder="AI That Works For You"
              />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">Title</label>
              <Input
                value={content.ai_editing.title}
                onChange={(e) => updateField('ai_editing.title', e.target.value)}
                placeholder="Edit in Real-Time While You Record"
              />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">Description</label>
              <Textarea
                value={content.ai_editing.description}
                onChange={(e) => updateField('ai_editing.description', e.target.value)}
                rows={3}
              />
            </div>
            <div>
              <label className="block text-sm font-medium mb-2">Bullet Points</label>
              {content.ai_editing.bullets.map((bullet, idx) => (
                <div key={idx} className="flex gap-2 mb-2">
                  <Textarea
                    value={bullet}
                    onChange={(e) => {
                      const newBullets = [...content.ai_editing.bullets];
                      newBullets[idx] = e.target.value;
                      updateField('ai_editing.bullets', newBullets);
                    }}
                    rows={2}
                  />
                  <Button 
                    variant="outline" 
                    size="sm"
                    onClick={() => {
                      const newBullets = content.ai_editing.bullets.filter((_, i) => i !== idx);
                      updateField('ai_editing.bullets', newBullets);
                    }}
                  >
                    Remove
                  </Button>
                </div>
              ))}
              <Button
                variant="outline"
                size="sm"
                onClick={() => updateField('ai_editing.bullets', [...content.ai_editing.bullets, ''])}
              >
                Add Bullet
              </Button>
            </div>
          </CardContent>
        )}
      </Card>

      {/* Done For You Section */}
      <Card>
        <CardHeader 
          className="cursor-pointer hover:bg-muted/50" 
          onClick={() => toggleSection('doneForYou')}
        >
          <div className="flex items-center justify-between">
            <div>
              <CardTitle>"Done For You, By You" Section</CardTitle>
              <CardDescription>3 pillars: Faster, Cheaper, Easier</CardDescription>
            </div>
            {expandedSections.doneForYou ? <ChevronUp /> : <ChevronDown />}
          </div>
        </CardHeader>
        {expandedSections.doneForYou && (
          <CardContent className="space-y-4">
            <div>
              <label className="block text-sm font-medium mb-1">Title</label>
              <Input
                value={content.done_for_you.title}
                onChange={(e) => updateField('done_for_you.title', e.target.value)}
                placeholder="Done For You,"
              />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">Title Highlight (red text)</label>
              <Input
                value={content.done_for_you.title_highlight}
                onChange={(e) => updateField('done_for_you.title_highlight', e.target.value)}
                placeholder="By You"
              />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">Description</label>
              <Textarea
                value={content.done_for_you.description}
                onChange={(e) => updateField('done_for_you.description', e.target.value)}
                rows={3}
              />
            </div>
            <div>
              <label className="block text-sm font-medium mb-2">Pillars (3 cards)</label>
              {content.done_for_you.pillars.map((pillar, idx) => (
                <Card key={idx} className="mb-3 bg-gray-50">
                  <CardContent className="pt-4">
                    <div className="space-y-3">
                      <Input
                        value={pillar.title}
                        onChange={(e) => updateArrayItem('done_for_you.pillars', idx, 'title', e.target.value)}
                        placeholder="Title (e.g., Faster)"
                        className="font-semibold"
                      />
                      <Textarea
                        value={pillar.description}
                        onChange={(e) => updateArrayItem('done_for_you.pillars', idx, 'description', e.target.value)}
                        rows={2}
                      />
                      <div className="flex gap-2">
                        <label className="text-sm">Color tone:</label>
                        <select
                          value={pillar.tone}
                          onChange={(e) => updateArrayItem('done_for_you.pillars', idx, 'tone', e.target.value)}
                          className="text-sm border rounded px-2"
                        >
                          <option value="primary">Primary</option>
                          <option value="secondary">Secondary</option>
                          <option value="accent">Accent</option>
                        </select>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          </CardContent>
        )}
      </Card>

      {/* Three Steps Section */}
      <Card>
        <CardHeader 
          className="cursor-pointer hover:bg-muted/50" 
          onClick={() => toggleSection('threeSteps')}
        >
          <div className="flex items-center justify-between">
            <div>
              <CardTitle>"3 Simple Steps" Section</CardTitle>
              <CardDescription>Record, Review, Publish steps</CardDescription>
            </div>
            {expandedSections.threeSteps ? <ChevronUp /> : <ChevronDown />}
          </div>
        </CardHeader>
        {expandedSections.threeSteps && (
          <CardContent className="space-y-4">
            <div>
              <label className="block text-sm font-medium mb-1">Title</label>
              <Input
                value={content.three_steps.title}
                onChange={(e) => updateField('three_steps.title', e.target.value)}
                placeholder="From Idea to Published in"
              />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">Title Highlight (red text)</label>
              <Input
                value={content.three_steps.title_highlight}
                onChange={(e) => updateField('three_steps.title_highlight', e.target.value)}
                placeholder="3 Simple Steps"
              />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">Description</label>
              <Textarea
                value={content.three_steps.description}
                onChange={(e) => updateField('three_steps.description', e.target.value)}
                rows={2}
              />
            </div>
            <div>
              <label className="block text-sm font-medium mb-2">Steps (numbered cards)</label>
              {content.three_steps.steps.map((step, idx) => (
                <Card key={idx} className="mb-3 bg-gray-50">
                  <CardContent className="pt-4">
                    <div className="space-y-3">
                      <div className="flex gap-2 items-center">
                        <span className="font-bold text-lg">Step {step.number}:</span>
                        <Input
                          value={step.title}
                          onChange={(e) => updateArrayItem('three_steps.steps', idx, 'title', e.target.value)}
                          placeholder="Title (e.g., Record)"
                          className="font-semibold"
                        />
                      </div>
                      <Textarea
                        value={step.description}
                        onChange={(e) => updateArrayItem('three_steps.steps', idx, 'description', e.target.value)}
                        rows={2}
                      />
                      <div className="flex gap-2">
                        <label className="text-sm">Color:</label>
                        <select
                          value={step.color}
                          onChange={(e) => updateArrayItem('three_steps.steps', idx, 'color', e.target.value)}
                          className="text-sm border rounded px-2"
                        >
                          <option value="primary">Primary</option>
                          <option value="secondary">Secondary</option>
                          <option value="accent">Accent</option>
                        </select>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">CTA Button Text</label>
              <Input
                value={content.three_steps.cta_text}
                onChange={(e) => updateField('three_steps.cta_text', e.target.value)}
                placeholder="Start Your First Episode Now"
              />
            </div>
          </CardContent>
        )}
      </Card>

      {/* Features Section */}
      <Card>
        <CardHeader 
          className="cursor-pointer hover:bg-muted/50" 
          onClick={() => toggleSection('features')}
        >
          <div className="flex items-center justify-between">
            <div>
              <CardTitle>Features Section</CardTitle>
              <CardDescription>6 feature cards (Unlimited Hosting, AI-Powered Editing, etc.)</CardDescription>
            </div>
            {expandedSections.features ? <ChevronUp /> : <ChevronDown />}
          </div>
        </CardHeader>
        {expandedSections.features && (
          <CardContent className="space-y-4">
            <div>
              <label className="block text-sm font-medium mb-1">Title</label>
              <Input
                value={content.features.title}
                onChange={(e) => updateField('features.title', e.target.value)}
                placeholder="Everything You Need to"
              />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">Title Highlight (red text)</label>
              <Input
                value={content.features.title_highlight}
                onChange={(e) => updateField('features.title_highlight', e.target.value)}
                placeholder="Succeed"
              />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">Description</label>
              <Textarea
                value={content.features.description}
                onChange={(e) => updateField('features.description', e.target.value)}
                rows={2}
              />
            </div>
            <div>
              <label className="block text-sm font-medium mb-2">Feature Cards</label>
              {content.features.features.map((feature, idx) => (
                <Card key={idx} className="mb-3 bg-gray-50">
                  <CardContent className="pt-4">
                    <div className="space-y-3">
                      <Input
                        value={feature.title}
                        onChange={(e) => updateArrayItem('features.features', idx, 'title', e.target.value)}
                        placeholder="Feature title"
                        className="font-semibold"
                      />
                      <Textarea
                        value={feature.description}
                        onChange={(e) => updateArrayItem('features.features', idx, 'description', e.target.value)}
                        rows={2}
                      />
                      <div className="flex gap-2">
                        <label className="text-sm">Color tone:</label>
                        <select
                          value={feature.tone}
                          onChange={(e) => updateArrayItem('features.features', idx, 'tone', e.target.value)}
                          className="text-sm border rounded px-2"
                        >
                          <option value="primary">Primary</option>
                          <option value="secondary">Secondary</option>
                          <option value="accent">Accent</option>
                        </select>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              ))}
              <Button
                variant="outline"
                size="sm"
                onClick={() => addArrayItem('features.features', { title: '', description: '', tone: 'primary' })}
              >
                Add Feature
              </Button>
            </div>
          </CardContent>
        )}
      </Card>

      {/* Why Section */}
      <Card>
        <CardHeader 
          className="cursor-pointer hover:bg-muted/50" 
          onClick={() => toggleSection('why')}
        >
          <div className="flex items-center justify-between">
            <div>
              <CardTitle>"Why Podcast Plus Plus?" Section</CardTitle>
              <CardDescription>4 differentiators (Patent-Pending Innovation, etc.)</CardDescription>
            </div>
            {expandedSections.why ? <ChevronUp /> : <ChevronDown />}
          </div>
        </CardHeader>
        {expandedSections.why && (
          <CardContent className="space-y-4">
            <div>
              <label className="block text-sm font-medium mb-1">Title Start</label>
              <Input
                value={content.why.title}
                onChange={(e) => updateField('why.title', e.target.value)}
                placeholder="Why"
              />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">Title Highlight (red text)</label>
              <Input
                value={content.why.title_highlight}
                onChange={(e) => updateField('why.title_highlight', e.target.value)}
                placeholder="Podcast Plus Plus"
              />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">Title Suffix</label>
              <Input
                value={content.why.title_suffix}
                onChange={(e) => updateField('why.title_suffix', e.target.value)}
                placeholder="?"
              />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">Description</label>
              <Textarea
                value={content.why.description}
                onChange={(e) => updateField('why.description', e.target.value)}
                rows={3}
              />
            </div>
            <div>
              <label className="block text-sm font-medium mb-2">Differentiators</label>
              {content.why.differentiators.map((diff, idx) => (
                <Card key={idx} className="mb-3 bg-gray-50">
                  <CardContent className="pt-4">
                    <div className="space-y-3">
                      <Input
                        value={diff.title}
                        onChange={(e) => updateArrayItem('why.differentiators', idx, 'title', e.target.value)}
                        placeholder="Title"
                        className="font-semibold"
                      />
                      <Textarea
                        value={diff.description}
                        onChange={(e) => updateArrayItem('why.differentiators', idx, 'description', e.target.value)}
                        rows={2}
                      />
                      <div className="flex gap-2">
                        <label className="text-sm">Color tone:</label>
                        <select
                          value={diff.tone}
                          onChange={(e) => updateArrayItem('why.differentiators', idx, 'tone', e.target.value)}
                          className="text-sm border rounded px-2"
                        >
                          <option value="primary">Primary</option>
                          <option value="secondary">Secondary</option>
                          <option value="accent">Accent</option>
                        </select>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              ))}
              <Button
                variant="outline"
                size="sm"
                onClick={() => addArrayItem('why.differentiators', { title: '', description: '', tone: 'primary' })}
              >
                Add Differentiator
              </Button>
            </div>
          </CardContent>
        )}
      </Card>

      {/* Final CTA Section */}
      <Card>
        <CardHeader 
          className="cursor-pointer hover:bg-muted/50" 
          onClick={() => toggleSection('finalCta')}
        >
          <div className="flex items-center justify-between">
            <div>
              <CardTitle>Final Call-to-Action Section</CardTitle>
              <CardDescription>Bottom CTA before footer</CardDescription>
            </div>
            {expandedSections.finalCta ? <ChevronUp /> : <ChevronDown />}
          </div>
        </CardHeader>
        {expandedSections.finalCta && (
          <CardContent className="space-y-4">
            <div>
              <label className="block text-sm font-medium mb-1">Pill Text</label>
              <Input
                value={content.final_cta.pill_text}
                onChange={(e) => updateField('final_cta.pill_text', e.target.value)}
                placeholder="Ready when you are"
              />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">Title</label>
              <Input
                value={content.final_cta.title}
                onChange={(e) => updateField('final_cta.title', e.target.value)}
                placeholder="Ready to Take Your Podcast to the Next Level?"
              />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">Description</label>
              <Textarea
                value={content.final_cta.description}
                onChange={(e) => updateField('final_cta.description', e.target.value)}
                rows={2}
              />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">CTA Button Text</label>
              <Input
                value={content.final_cta.cta_text}
                onChange={(e) => updateField('final_cta.cta_text', e.target.value)}
                placeholder="Start Your Free Trial"
              />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">Fine Print (below button)</label>
              <Input
                value={content.final_cta.fine_print}
                onChange={(e) => updateField('final_cta.fine_print', e.target.value)}
                placeholder="14-day free trial • No credit card required • Cancel anytime"
              />
            </div>
          </CardContent>
        )}
      </Card>

      {/* Reviews/Testimonials Section */}
      <Card>
        <CardHeader 
          className="cursor-pointer hover:bg-muted/50" 
          onClick={() => toggleSection('reviews')}
        >
          <div className="flex items-center justify-between">
            <div>
              <CardTitle>Customer Reviews/Testimonials</CardTitle>
              <CardDescription>Social proof section with star ratings</CardDescription>
            </div>
            {expandedSections.reviews ? <ChevronUp /> : <ChevronDown />}
          </div>
        </CardHeader>
        {expandedSections.reviews && (
          <CardContent className="space-y-4">
            <div>
              <label className="block text-sm font-medium mb-1">Section Heading</label>
              <Input
                value={content.reviews_heading}
                onChange={(e) => updateField('reviews_heading', e.target.value)}
                placeholder="Real Stories from Real Podcasters"
              />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">Summary (e.g., average rating)</label>
              <Input
                value={content.reviews_summary}
                onChange={(e) => updateField('reviews_summary', e.target.value)}
                placeholder="4.9/5 from 2,847 reviews"
              />
            </div>
            <div>
              <label className="block text-sm font-medium mb-2">Reviews</label>
              {content.reviews.map((review, idx) => (
                <Card key={idx} className="mb-3 bg-gray-50">
                  <CardContent className="pt-4">
                    <div className="space-y-3">
                      <Textarea
                        value={review.quote}
                        onChange={(e) => updateArrayItem('reviews', idx, 'quote', e.target.value)}
                        placeholder="Customer quote..."
                        rows={3}
                      />
                      <Input
                        value={review.author}
                        onChange={(e) => updateArrayItem('reviews', idx, 'author', e.target.value)}
                        placeholder="Customer name"
                      />
                      <Input
                        value={review.role || ''}
                        onChange={(e) => updateArrayItem('reviews', idx, 'role', e.target.value)}
                        placeholder="Role/title (optional)"
                      />
                      <Input
                        value={review.avatar_url || ''}
                        onChange={(e) => updateArrayItem('reviews', idx, 'avatar_url', e.target.value)}
                        placeholder="Avatar image URL (optional)"
                      />
                      <div className="flex gap-2 items-center">
                        <label className="text-sm">Rating (0-5):</label>
                        <Input
                          type="number"
                          min="0"
                          max="5"
                          step="0.1"
                          value={review.rating || 5}
                          onChange={(e) => updateArrayItem('reviews', idx, 'rating', parseFloat(e.target.value))}
                          className="w-20"
                        />
                        <Button 
                          variant="outline" 
                          size="sm"
                          onClick={() => removeArrayItem('reviews', idx)}
                        >
                          Remove Review
                        </Button>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              ))}
              <Button
                variant="outline"
                size="sm"
                onClick={() => addArrayItem('reviews', { quote: '', author: '', role: '', avatar_url: '', rating: 5 })}
              >
                Add Review
              </Button>
            </div>
          </CardContent>
        )}
      </Card>

      {/* FAQs Section */}
      <Card>
        <CardHeader 
          className="cursor-pointer hover:bg-muted/50" 
          onClick={() => toggleSection('faqs')}
        >
          <div className="flex items-center justify-between">
            <div>
              <CardTitle>Frequently Asked Questions (FAQs)</CardTitle>
              <CardDescription>Accordion section with Q&A</CardDescription>
            </div>
            {expandedSections.faqs ? <ChevronUp /> : <ChevronDown />}
          </div>
        </CardHeader>
        {expandedSections.faqs && (
          <CardContent className="space-y-4">
            <div>
              <label className="block text-sm font-medium mb-1">Section Heading</label>
              <Input
                value={content.faq_heading}
                onChange={(e) => updateField('faq_heading', e.target.value)}
                placeholder="Frequently Asked Questions"
              />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">Subheading</label>
              <Input
                value={content.faq_subheading}
                onChange={(e) => updateField('faq_subheading', e.target.value)}
                placeholder="Everything you need to know..."
              />
            </div>
            <div>
              <label className="block text-sm font-medium mb-2">FAQ Items</label>
              {content.faqs.map((faq, idx) => (
                <Card key={idx} className="mb-3 bg-gray-50">
                  <CardContent className="pt-4">
                    <div className="space-y-3">
                      <Input
                        value={faq.question}
                        onChange={(e) => updateArrayItem('faqs', idx, 'question', e.target.value)}
                        placeholder="Question"
                        className="font-semibold"
                      />
                      <Textarea
                        value={faq.answer}
                        onChange={(e) => updateArrayItem('faqs', idx, 'answer', e.target.value)}
                        placeholder="Answer"
                        rows={3}
                      />
                      <Button 
                        variant="outline" 
                        size="sm"
                        onClick={() => removeArrayItem('faqs', idx)}
                      >
                        Remove FAQ
                      </Button>
                    </div>
                  </CardContent>
                </Card>
              ))}
              <Button
                variant="outline"
                size="sm"
                onClick={() => addArrayItem('faqs', { question: '', answer: '' })}
              >
                Add FAQ
              </Button>
            </div>
          </CardContent>
        )}
      </Card>

      {/* Bottom save button */}
      <div className="flex gap-2 pb-8">
        <Button onClick={handleSave} disabled={saving}>
          {saving ? (
            <>
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              Saving...
            </>
          ) : (
            <>
              <Save className="mr-2 h-4 w-4" />
              Save All Changes
            </>
          )}
        </Button>
        
        {success && (
          <Alert className="py-2 border-green-500 bg-green-50">
            <AlertDescription className="text-green-700">
              Changes saved successfully!
            </AlertDescription>
          </Alert>
        )}
      </div>
    </div>
  );
}
