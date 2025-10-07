import React from 'react';
import { useBrand } from '@/brand/BrandContext.jsx';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { FileText, Shield, Award } from 'lucide-react';

export default function LegalPage() {
  const { brand } = useBrand();

  return (
    <div className="min-h-screen bg-background">
      <div className="container mx-auto px-4 py-12 max-w-4xl">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-4xl font-bold mb-2">Legal Information</h1>
          <p className="text-muted-foreground">
            Intellectual property and legal notices for {brand.name}
          </p>
        </div>

        {/* Patent Information */}
        <Card className="mb-6">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Award className="w-5 h-5" />
              Patent Information
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div>
              <h3 className="font-semibold mb-2">Voice-Driven Real-Time Podcast Editing and Assembly System</h3>
              <div className="space-y-2 text-sm">
                <div className="grid grid-cols-[140px_1fr] gap-2">
                  <span className="text-muted-foreground">Status:</span>
                  <span className="font-medium">Patent Pending</span>
                </div>
                <div className="grid grid-cols-[140px_1fr] gap-2">
                  <span className="text-muted-foreground">Application Type:</span>
                  <span>Utility - Provisional Application under 35 USC 111(b)</span>
                </div>
                <div className="grid grid-cols-[140px_1fr] gap-2">
                  <span className="text-muted-foreground">Application Number:</span>
                  <span className="font-mono">63/894,250</span>
                </div>
                <div className="grid grid-cols-[140px_1fr] gap-2">
                  <span className="text-muted-foreground">Filing Date:</span>
                  <span>October 6, 2025</span>
                </div>
                <div className="grid grid-cols-[140px_1fr] gap-2">
                  <span className="text-muted-foreground">Patent Center #:</span>
                  <span className="font-mono">72593784</span>
                </div>
                <div className="grid grid-cols-[140px_1fr] gap-2">
                  <span className="text-muted-foreground">Confirmation #:</span>
                  <span className="font-mono">5417</span>
                </div>
                <div className="grid grid-cols-[140px_1fr] gap-2">
                  <span className="text-muted-foreground">Inventor:</span>
                  <span>Benjamin Scott Gerhardt</span>
                </div>
              </div>
            </div>

            <div className="pt-4 border-t">
              <h4 className="font-semibold mb-2 text-sm">What is Protected</h4>
              <p className="text-sm text-muted-foreground">
                This provisional patent application covers our innovative voice-driven podcast editing and assembly technology, including:
              </p>
              <ul className="list-disc list-inside text-sm text-muted-foreground mt-2 space-y-1 ml-4">
                <li>Real-time voice command processing during recording ("Flubber", "Intern" commands)</li>
                <li>AI-powered audio assembly and editing automation</li>
                <li>Template-based episode structure with dynamic segment management</li>
                <li>Integrated TTS generation and background music mixing</li>
                <li>Automated audio cleanup and enhancement pipelines</li>
              </ul>
            </div>

            <div className="pt-4 border-t">
              <p className="text-xs text-muted-foreground italic">
                A provisional patent application establishes an early filing date and provides "Patent Pending" status
                for 12 months while a non-provisional application is prepared. This protects our intellectual property
                as we continue to develop and refine the technology.
              </p>
            </div>
          </CardContent>
        </Card>

        {/* Copyright */}
        <Card className="mb-6">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <FileText className="w-5 h-5" />
              Copyright
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground">
              © {new Date().getFullYear()} {brand.name}. All rights reserved.
            </p>
            <p className="text-sm text-muted-foreground mt-2">
              The {brand.name} software, user interface, documentation, and all related content are protected
              by copyright law. Unauthorized reproduction, distribution, or modification is prohibited.
            </p>
          </CardContent>
        </Card>

        {/* Trademark */}
        <Card className="mb-6">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Shield className="w-5 h-5" />
              Trademarks
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground">
              {brand.name}, {brand.shortName}++, and related logos are trademarks or registered trademarks
              of Benjamin Scott Gerhardt. All other trademarks mentioned are the property of their respective owners.
            </p>
          </CardContent>
        </Card>

        {/* Contact */}
        <Card>
          <CardHeader>
            <CardTitle>Contact Information</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2 text-sm">
              <div className="grid grid-cols-[140px_1fr] gap-2">
                <span className="text-muted-foreground">Correspondence:</span>
                <div>
                  <div>Benjamin Scott Gerhardt</div>
                  <div>Scott Gerhardt</div>
                  <div>121 W Lexington Dr, Suite 236</div>
                  <div>Glendale, CA 91203</div>
                  <div>United States</div>
                </div>
              </div>
              <div className="grid grid-cols-[140px_1fr] gap-2 mt-4">
                <span className="text-muted-foreground">Legal Inquiries:</span>
                <a href="mailto:legal@podcastplusplus.ai" className="text-primary hover:underline">
                  legal@podcastplusplus.ai
                </a>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Quick Links */}
        <div className="mt-8 flex justify-center gap-4 text-sm">
          <a href="/privacy" className="text-muted-foreground hover:text-foreground">
            Privacy Policy
          </a>
          <span className="text-muted-foreground">•</span>
          <a href="/terms" className="text-muted-foreground hover:text-foreground">
            Terms of Use
          </a>
          <span className="text-muted-foreground">•</span>
          <a href="/" className="text-muted-foreground hover:text-foreground">
            Back to Home
          </a>
        </div>
      </div>
    </div>
  );
}
