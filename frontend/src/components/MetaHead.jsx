import React, { useEffect } from "react";

/**
 * MetaHead: lightweight document head manager.
 * - Sets document.title
 * - Ensures OG/Twitter meta tags exist and reflect provided props
 * Defaults to brand-safe values when props are omitted.
 */
export default function MetaHead({ title, description, image, url }) {
  const defaultTitle = "DoneCast";
  const defaultDescription = "Professional podcast hosting for the modern creator.";
  const defaultImage = "/assets/branding/logo-horizontal.png";
  const defaultUrl = typeof window !== 'undefined' ? window.location.origin : 'https://donecast.com';

  useEffect(() => {
    const finalTitle = title || defaultTitle;
    const finalDescription = description || defaultDescription;
    const finalImage = image || defaultImage;
    const finalUrl = url || defaultUrl;

    if (finalTitle) document.title = finalTitle;

    const ensureMeta = (attr, key, value) => {
      if (!value) return;
      let el = document.querySelector(`meta[${attr}='${key}']`);
      if (!el) {
        el = document.createElement('meta');
        el.setAttribute(attr, key);
        document.head.appendChild(el);
      }
      el.setAttribute('content', value);
    };

    // Open Graph
    ensureMeta('property', 'og:type', 'website');
    ensureMeta('property', 'og:site_name', 'DoneCast');
    ensureMeta('property', 'og:title', finalTitle);
    ensureMeta('property', 'og:description', finalDescription);
    ensureMeta('property', 'og:url', finalUrl);
    ensureMeta('property', 'og:image', finalImage);
    ensureMeta('property', 'og:image:alt', finalTitle);

    // Twitter Card
    ensureMeta('name', 'twitter:card', 'summary_large_image');
    ensureMeta('name', 'twitter:title', finalTitle);
    ensureMeta('name', 'twitter:description', finalDescription);
    ensureMeta('name', 'twitter:image', finalImage);
  }, [title, description, image, url]);

  return null;
}
