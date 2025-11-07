import React from "react";
import PropTypes from "prop-types";
import { formatInTimezone } from "@/lib/timezone";

/**
 * AdminHeader - Renders the top header for the admin dashboard
 * Shows active tab title, description, brand, and timestamp
 * 
 * @param {string} activeTab - Currently active tab ID
 * @param {Array} navigationItems - Array of nav items to lookup labels
 * @param {string} resolvedTimezone - Timezone for displaying timestamp
 */
export default function AdminHeader({ activeTab, navigationItems, resolvedTimezone }) {
  const currentNav = navigationItems.find((item) => item.id === activeTab);
  
  const getTabDescription = (tabId) => {
    const descriptions = {
      users: "Manage platform users and their accounts",
      analytics: "Monitor platform performance and user engagement",
      bugs: "View and manage bug reports and user feedback from Mike",
      tiers: "Configure tier features, credits, and processing pipelines (database-driven)",
      db: "Browse & edit core tables (safe fields only)",
      music: "Curate previewable background tracks for onboarding/templates",
      settings: "Configure platform settings and features",
      dashboard: "Overview of platform metrics and activity",
      landing: "Customize landing page reviews, FAQs, and hero messaging",
      billing: "View and manage billing details and subscriptions",
      podcasts: "View and manage all podcasts on the platform",
      help: "Access help documentation and resources",
    };
    return descriptions[tabId] || "";
  };

  return (
    <header className="bg-white border-b border-gray-200 px-6 py-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold" style={{ color: "#2C3E50" }}>
            {currentNav?.label || "Admin Dashboard"}
          </h1>
          <p className="text-gray-600 mt-1">
            {getTabDescription(activeTab)}
          </p>
        </div>
        <div className="flex items-center space-x-4">
          <div className="text-xs px-2 py-1 rounded bg-secondary text-secondary-foreground">
            Brand: {document.documentElement.getAttribute("data-brand") || "ppp"}
          </div>
          <div className="text-sm text-gray-600">
            Last updated: {formatInTimezone(new Date(), { timeStyle: 'medium' }, resolvedTimezone)}
          </div>
        </div>
      </div>
    </header>
  );
}

AdminHeader.propTypes = {
  activeTab: PropTypes.string.isRequired,
  navigationItems: PropTypes.arrayOf(
    PropTypes.shape({
      id: PropTypes.string.isRequired,
      label: PropTypes.string.isRequired,
    })
  ).isRequired,
  resolvedTimezone: PropTypes.string.isRequired,
};
