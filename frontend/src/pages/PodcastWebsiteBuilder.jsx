import LegalLayout from "@/pages/LegalLayout.jsx";

const html = `
  <h1>Podcast Website Builder Guide</h1>
  <p>Whether you are a seasoned producer or helping a 70-year-old first-time podcaster, the builder is designed to feel conversational and forgiving.</p>
  <h2>No-code quick start</h2>
  <ol>
    <li><strong>Sign in</strong> to DoneCast and open the podcast you want to publish.</li>
    <li><strong>Click “Website Builder”</strong> in the left navigation. A friendly chat panel opens next to a live preview of the site.</li>
    <li><strong>Press “Create my site.”</strong> The AI looks at your show description, hosts, and recent episodes, then drafts a complete page with hero copy, an About section, host bios, and a playable episode grid.</li>
    <li><strong>Talk to the AI like a helper.</strong> Try requests such as:
      <ul>
        <li>“Make the hero photo brighter and add a bigger play button.”</li>
        <li>“Add a section inviting people to join my newsletter.”</li>
        <li>“Change the colors to navy and gold.”</li>
      </ul>
      The builder remembers each message so you can refine the page step by step.
    </li>
    <li><strong>Share immediately.</strong> The builder publishes to <code>https://&lt;yourshow&gt;.donecast.com</code> as soon as the first draft is ready.</li>
    <li><strong>Use your own domain (Pro tier and above).</strong> Type “Help me use my custom domain.” The assistant walks you through adding a CNAME record and confirms when DNS has finished propagating.</li>
  </ol>
  <h3>Tips for non-technical hosts</h3>
  <ul>
    <li><strong>Plain language works best.</strong> There are no commands to memorize—just describe what you want to see.</li>
    <li><strong>Undo is built in.</strong> Say “Undo that change” or “Go back to the version from this morning” to reload a saved layout.</li>
    <li><strong>Accessibility checks run automatically.</strong> The builder keeps text large and color contrast compliant.</li>
    <li><strong>Help bubble videos.</strong> Tooltips include short recordings that demonstrate each step for clients who like visual guidance.</li>
  </ul>
  <h2>Admin &amp; support workflow</h2>
  <ul>
    <li><strong>Saved prompt history.</strong> Every chat turn is stored with timestamps under the <code>prompts/</code> prefix of the <code>ppp-websites-us-west1</code> bucket so support can review changes.</li>
    <li><strong>One-click restore.</strong> Support agents can select an earlier prompt in the dashboard to roll the site back.</li>
    <li><strong>Email summaries.</strong> When a site is published we send the owner a recap with the live URL, DNS instructions, and the final prompt transcript.</li>
  </ul>
  <h2>API endpoints</h2>
  <p>The same workflow is available programmatically. All endpoints live under <code>/api/podcasts/{podcast_id}/website</code> and require authentication with the owning user account.</p>
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
  <p>After generation, the site is available at <code>https://&lt;subdomain&gt;.{BASE_DOMAIN}</code> where <code>{BASE_DOMAIN}</code> defaults to <code>donecast.com</code> but can be overridden through the <code>PODCAST_WEBSITE_BASE_DOMAIN</code> configuration. The API response also includes any configured custom domain when one is attached.</p>
  <h2>Saved prompts</h2>
  <p>Every AI generation request stores the prompt, response, and metadata (when <code>PODCAST_WEBSITE_GCS_BUCKET</code> is configured) under the <code>prompts/</code> prefix of the <code>ppp-websites-us-west1</code> bucket for review.</p>
`;

export default function PodcastWebsiteBuilder() {
  return (
    <LegalLayout
      title="Podcast Website Builder Guide"
      description="Learn how to launch and customize DoneCast AI-powered podcast websites without code."
      html={html}
    />
  );
}
