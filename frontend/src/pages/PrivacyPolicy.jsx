import LegalLayout from "./LegalLayout.jsx";
import privacyHtml from "@/legal/privacy-policy.html?raw";

export default function PrivacyPolicy() {
  return (
    <LegalLayout
      title="Privacy Policy"
      description="Learn how DoneCast collects, uses, and protects your information."
      html={privacyHtml}
    />
  );
}
