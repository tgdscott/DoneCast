import LegalLayout from "./LegalLayout.jsx";
import privacyHtml from "@/legal/privacy-policy.html?raw";

export default function PrivacyPolicy() {
  return (
    <LegalLayout
      title="Privacy Policy"
      description="Learn how Podcast Plus Plus collects, uses, and protects your information."
      html={privacyHtml}
    />
  );
}
