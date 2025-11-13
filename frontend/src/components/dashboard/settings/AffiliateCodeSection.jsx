import React, { useState, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Copy, Check, Share2, Users } from "lucide-react";
import { useToast } from "@/hooks/use-toast";
import { buildApiUrl } from "@/lib/apiClient.js";
import { SectionCard, SectionItem } from "@/components/dashboard/SettingsSections";

const apiUrl = (path) => buildApiUrl(path);

export default function AffiliateCodeSection({ token }) {
  const { toast } = useToast();
  const [affiliateCode, setAffiliateCode] = useState(null);
  const [loading, setLoading] = useState(true);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    fetchAffiliateCode();
  }, []);

  const fetchAffiliateCode = async () => {
    try {
      setLoading(true);
      const response = await fetch(apiUrl("/api/affiliate/me"), {
        headers: {
          Authorization: `Bearer ${token}`,
        },
      });
      if (!response.ok) throw new Error("Failed to fetch affiliate code");
      const data = await response.json();
      setAffiliateCode(data);
    } catch (error) {
      toast({
        title: "Error",
        description: error.message,
        variant: "destructive",
      });
    } finally {
      setLoading(false);
    }
  };

  const handleCopyLink = async () => {
    if (!affiliateCode?.referral_link) return;
    try {
      await navigator.clipboard.writeText(affiliateCode.referral_link);
      setCopied(true);
      toast({
        title: "Copied!",
        description: "Referral link copied to clipboard",
      });
      setTimeout(() => setCopied(false), 2000);
    } catch (error) {
      toast({
        title: "Error",
        description: "Failed to copy link",
        variant: "destructive",
      });
    }
  };

  const handleCopyCode = async () => {
    if (!affiliateCode?.code) return;
    try {
      await navigator.clipboard.writeText(affiliateCode.code);
      setCopied(true);
      toast({
        title: "Copied!",
        description: "Referral code copied to clipboard",
      });
      setTimeout(() => setCopied(false), 2000);
    } catch (error) {
      toast({
        title: "Error",
        description: "Failed to copy code",
        variant: "destructive",
      });
    }
  };

  if (loading) {
    return (
      <div className="space-y-6">
        <div className="space-y-2">
          <h2 className="text-2xl font-bold text-gray-900">Referral Program</h2>
          <p className="text-gray-600">Share your referral link and earn rewards.</p>
        </div>
        <div className="text-center py-12">Loading...</div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <h2 className="text-2xl font-bold text-gray-900">Referral Program</h2>
        <p className="text-gray-600">Share your referral link and earn rewards when friends sign up.</p>
      </div>

      <SectionCard
        icon={<Share2 className="h-5 w-5 text-white" />}
        title="Your Referral Code"
        subtitle="Share this link with friends to earn rewards"
        defaultOpen
      >
        <SectionItem
          icon={<Share2 className="h-4 w-4 text-white" />}
          title="Referral Link"
          description="Share this link with friends. When they sign up, you'll get credit for the referral."
        >
          <div className="space-y-4">
            <div className="flex items-center gap-2">
              <Input
                value={affiliateCode?.referral_link || ""}
                readOnly
                className="font-mono text-sm"
              />
              <Button
                onClick={handleCopyLink}
                variant="outline"
                size="sm"
                className="gap-2"
              >
                {copied ? (
                  <>
                    <Check className="w-4 h-4" />
                    Copied!
                  </>
                ) : (
                  <>
                    <Copy className="w-4 h-4" />
                    Copy Link
                  </>
                )}
              </Button>
            </div>
            <p className="text-xs text-muted-foreground">
              When someone clicks your link and signs up, their referral will be automatically tracked.
            </p>
          </div>
        </SectionItem>

        <SectionItem
          icon={<Users className="h-4 w-4 text-white" />}
          title="Your Referral Code"
          description="Your unique referral code"
        >
          <div className="space-y-4">
            <div className="flex items-center gap-2">
              <Input
                value={affiliateCode?.code || ""}
                readOnly
                className="font-mono text-lg font-bold text-center max-w-xs"
              />
              <Button
                onClick={handleCopyCode}
                variant="outline"
                size="sm"
                className="gap-2"
              >
                {copied ? (
                  <>
                    <Check className="w-4 h-4" />
                    Copied!
                  </>
                ) : (
                  <>
                    <Copy className="w-4 h-4" />
                    Copy Code
                  </>
                )}
              </Button>
            </div>
            <p className="text-xs text-muted-foreground">
              People can enter this code manually during signup if they don't use your link.
            </p>
          </div>
        </SectionItem>

        <SectionItem
          icon={<Users className="h-4 w-4 text-white" />}
          title="Referral Stats"
          description="Track your referral performance"
        >
          <div className="space-y-2">
            <div className="flex items-center justify-between p-4 bg-gray-50 rounded-lg">
              <span className="text-sm font-medium text-gray-700">Total Referrals</span>
              <span className="text-2xl font-bold text-gray-900">{affiliateCode?.referral_count || 0}</span>
            </div>
            <p className="text-xs text-muted-foreground">
              Number of users who have signed up using your referral code.
            </p>
          </div>
        </SectionItem>
      </SectionCard>
    </div>
  );
}

