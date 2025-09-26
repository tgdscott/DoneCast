import LegalLayout from "./LegalLayout.jsx";
import termsHtml from "@/legal/terms-of-use.html?raw";

export default function TermsOfUse() {
  return (
    <LegalLayout
      title="Terms of Use"
      description="Review the Podcast Plus Plus terms that govern access to our services."
      html={termsHtml}
    />
  );
}
