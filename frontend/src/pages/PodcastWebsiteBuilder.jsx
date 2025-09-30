import LegalLayout from "@/pages/LegalLayout.jsx";

const html = `
  <h1>Podcast Website Builder Access Guide</h1>
  <p>The podcast website builder is exposed through the Podcasts API and serves generated pages via subdomains of the configured base domain.</p>
  <h2>API endpoints</h2>
  <p>All endpoints live under <code>/api/podcasts/{podcast_id}/website</code> and require authentication with the owning user account.</p>
  <table>
    <thead>
      <tr>
        <th>Method &amp; Path</th>
        <th>Purpose</th>
      </tr>
    </thead>
    <tbody>
      <tr>
        <td><code>GET /api/podcasts/{podcast_id}/website</code></td>
        <td>Fetch the current website metadata, layout JSON, status, and domains.</td>
      </tr>
      <tr>
        <td><code>POST /api/podcasts/{podcast_id}/website</code></td>
        <td>Invoke Gemini to create or refresh the website layout.</td>
      </tr>
      <tr>
        <td><code>POST /api/podcasts/{podcast_id}/website/chat</code></td>
        <td>Send a natural-language instruction to the AI builder and receive the updated layout.</td>
      </tr>
      <tr>
        <td><code>PATCH /api/podcasts/{podcast_id}/website/domain</code></td>
        <td>Set or clear a custom domain (subject to plan tier requirements).</td>
      </tr>
    </tbody>
  </table>
  <p>The JSON response includes the internal <code>subdomain</code> and the computed <code>default_domain</code> that the static site is served from.</p>
  <h2>Viewing the generated site</h2>
  <p>After generation, the site is available at <code>https://&lt;subdomain&gt;.{BASE_DOMAIN}</code> where <code>{BASE_DOMAIN}</code> defaults to <code>podcastplusplus.com</code> but can be overridden through the <code>PODCAST_WEBSITE_BASE_DOMAIN</code> configuration. The API response also includes any configured custom domain when one is attached.</p>
  <h2>Saved prompts</h2>
  <p>Every AI generation request stores the prompt, response, and metadata (when <code>PODCAST_WEBSITE_GCS_BUCKET</code> is configured) under the <code>prompts/</code> prefix of the <code>ppp-websites-us-west1</code> bucket for review.</p>
`;

export default function PodcastWebsiteBuilder() {
  return (
    <LegalLayout
      title="Podcast Website Builder Guide"
      description="Learn how to access the Podcast Plus Plus AI-powered podcast website builder."
      html={html}
    />
  );
}
