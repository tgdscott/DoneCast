import { useState } from 'react';
import { useAuth } from '../AuthContext';
import { Card, CardHeader, CardTitle, CardContent } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Textarea } from '../components/ui/textarea';
import { Label } from '../components/ui/label';
import { useToast } from '../hooks/use-toast';
import { makeApi } from '../lib/apiClient';
import { ArrowLeft, Mail, Send } from 'lucide-react';
import { useNavigate } from 'react-router-dom';

export default function Contact() {
  const { token, user } = useAuth();
  const { toast } = useToast();
  const navigate = useNavigate();
  const [loading, setLoading] = useState(false);
  const [formData, setFormData] = useState({
    name: user?.full_name || user?.email?.split('@')[0] || '',
    email: user?.email || '',
    subject: 'general',
    message: ''
  });

  const subjects = [
    { value: 'general', label: 'General Inquiry' },
    { value: 'technical', label: 'Technical Support' },
    { value: 'billing', label: 'Billing Question' },
    { value: 'feature', label: 'Feature Request' },
    { value: 'bug', label: 'Report a Bug' },
    { value: 'account', label: 'Account Issue' },
    { value: 'feedback', label: 'Feedback' }
  ];

  const handleChange = (e) => {
    const { name, value } = e.target;
    setFormData(prev => ({ ...prev, [name]: value }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    
    if (!formData.name.trim()) {
      toast({ title: 'Name required', description: 'Please enter your name', variant: 'destructive' });
      return;
    }
    
    if (!formData.email.trim() || !formData.email.includes('@')) {
      toast({ title: 'Valid email required', description: 'Please enter a valid email address', variant: 'destructive' });
      return;
    }
    
    if (!formData.message.trim()) {
      toast({ title: 'Message required', description: 'Please tell us how we can help', variant: 'destructive' });
      return;
    }

    setLoading(true);
    try {
      const api = makeApi(token);
      await api.post('/api/contact', formData);
      
      toast({
        title: 'Message sent!',
        description: "We'll get back to you as soon as possible.",
      });
      
      setFormData(prev => ({ ...prev, subject: 'general', message: '' }));
      
      // Redirect to dashboard after 2 seconds
      setTimeout(() => {
        navigate('/dashboard');
      }, 2000);
    } catch (err) {
      console.error('[Contact] Submit error:', err);
      toast({
        title: 'Failed to send message',
        description: err?.message || 'Please try again or email us directly at support@podcastplusplus.com',
        variant: 'destructive'
      });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gray-50 py-8 px-4">
      <div className="max-w-2xl mx-auto">
        <Button
          variant="ghost"
          className="mb-4"
          onClick={() => navigate(-1)}
        >
          <ArrowLeft className="h-4 w-4 mr-2" />
          Back
        </Button>

        <Card>
          <CardHeader>
            <div className="flex items-center gap-3">
              <Mail className="h-6 w-6 text-primary" />
              <CardTitle>Contact Us</CardTitle>
            </div>
            <p className="text-sm text-muted-foreground mt-2">
              Have a question or need help? Fill out the form below and we'll get back to you as soon as possible.
            </p>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleSubmit} className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="name">Name</Label>
                <Input
                  id="name"
                  name="name"
                  type="text"
                  placeholder="Your name"
                  value={formData.name}
                  onChange={handleChange}
                  required
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="email">Email</Label>
                <Input
                  id="email"
                  name="email"
                  type="email"
                  placeholder="your@email.com"
                  value={formData.email}
                  onChange={handleChange}
                  required
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="subject">What's this about?</Label>
                <select
                  id="subject"
                  name="subject"
                  value={formData.subject}
                  onChange={handleChange}
                  className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
                  required
                >
                  {subjects.map(s => (
                    <option key={s.value} value={s.value}>
                      {s.label}
                    </option>
                  ))}
                </select>
              </div>

              <div className="space-y-2">
                <Label htmlFor="message">Message</Label>
                <Textarea
                  id="message"
                  name="message"
                  placeholder="Tell us how we can help..."
                  value={formData.message}
                  onChange={handleChange}
                  rows={6}
                  required
                />
              </div>

              <div className="flex gap-3 pt-2">
                <Button
                  type="submit"
                  disabled={loading}
                  className="flex-1"
                >
                  {loading ? (
                    <>Sending...</>
                  ) : (
                    <>
                      <Send className="h-4 w-4 mr-2" />
                      Send Message
                    </>
                  )}
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => navigate(-1)}
                  disabled={loading}
                >
                  Cancel
                </Button>
              </div>
            </form>

            <div className="mt-6 pt-6 border-t">
              <p className="text-sm text-muted-foreground text-center">
                You can also email us directly at{' '}
                <a
                  href="mailto:support@podcastplusplus.com"
                  className="text-primary hover:underline"
                >
                  support@podcastplusplus.com
                </a>
              </p>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
