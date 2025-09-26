import MetaHead from "@/components/MetaHead.jsx";
import Logo from "@/components/Logo.jsx";

const currentYear = new Date().getFullYear();

export default function LegalLayout({ title, description, html }) {
  const metaDescription = description || `Read the Podcast Plus Plus ${title}.`;

  return (
    <div className="min-h-screen bg-slate-100 text-slate-900">
      <MetaHead title={`${title} | Podcast Plus Plus`} description={metaDescription} />

      <header className="border-b bg-white">
        <div className="mx-auto flex max-w-5xl items-center justify-between px-6 py-4">
          <a href="/" className="flex items-center gap-3 text-slate-900 no-underline hover:opacity-80" aria-label="Podcast Plus Plus home">
            <Logo size={32} />
          </a>
          <a href="/?login=1" className="text-sm font-medium text-blue-600 transition-colors hover:text-blue-700">
            Sign In
          </a>
        </div>
      </header>

      <main className="mx-auto max-w-5xl px-6 py-16">
        <article className="legal-content" dangerouslySetInnerHTML={{ __html: html }} />
      </main>

      <footer className="border-t bg-white">
        <div className="mx-auto flex max-w-5xl flex-col gap-3 px-6 py-6 text-sm text-slate-500 md:flex-row md:items-center md:justify-between">
          <span> {currentYear} Podcast Plus Plus. All rights reserved.</span>
          <nav className="flex flex-wrap gap-x-4 gap-y-2">
            <a href="/privacy" className="transition-colors hover:text-slate-700">
              Privacy Policy
            </a>
            <a href="/terms" className="transition-colors hover:text-slate-700">
              Terms of Use
            </a>
          </nav>
        </div>
      </footer>
    </div>
  );
}
