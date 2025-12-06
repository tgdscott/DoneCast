import React from "react";
import PropTypes from "prop-types";
import { Button } from "@/components/ui/button";
import Logo from "@/components/Logo.jsx";

/**
 * DashboardSidebar - shared navigation for the DoneCast dashboard experience.
 * Mirrors the admin sidebar structure (static top + scrolling content) but with
 * customer-facing sections and a Guides block separated below the core tools.
 */
export default function DashboardSidebar({
  navItems,
  activeView,
  onNavigate,
  onLogout,
  className = "",
}) {
  const primaryItems = navItems.filter((item) => item.section !== "support");
  const supportItems = navItems.filter((item) => item.section === "support");

  const handleItemClick = (item) => {
    if (item.disabled) return;
    if (item.href) {
      window.location.href = item.href;
      return;
    }
    onNavigate?.(item);
  };

  return (
    <aside
      className={`hidden lg:flex w-64 flex-shrink-0 bg-white border-r border-gray-200 flex-col ${className}`}
      aria-label="Dashboard navigation"
    >
      <div className="px-6 py-5 border-b border-gray-200">
        <Logo size={32} />
      </div>

      <nav className="flex-1 overflow-y-auto px-4 py-6" role="navigation">
        <ul className="space-y-2">
          {primaryItems.map((item) => (
            <li key={item.id}>
              <button
                type="button"
                onClick={() => handleItemClick(item)}
                data-tour-id={item.tourId}
                className={`w-full flex items-center gap-3 px-4 py-3 rounded-lg text-left transition-all text-sm font-medium ${
                  activeView === item.view
                    ? "text-white shadow-md"
                    : "text-gray-600 hover:bg-gray-100 hover:text-gray-900"
                } ${item.disabled ? "opacity-50 cursor-not-allowed" : ""}`}
                style={{
                  backgroundColor: activeView === item.view ? "#2C3E50" : "transparent",
                }}
                aria-current={activeView === item.view ? "page" : undefined}
                aria-disabled={item.disabled ? "true" : "false"}
              >
                {item.icon && <item.icon className="w-4 h-4" />}
                <span>{item.label}</span>
              </button>
            </li>
          ))}
        </ul>

        {supportItems.length > 0 && (
          <div className="mt-10 pt-6 border-t border-dashed border-gray-200">
            <ul className="space-y-2">
              {supportItems.map((item) => (
                <li key={item.id}>
                  <button
                    type="button"
                    onClick={() => handleItemClick(item)}
                    data-tour-id={item.tourId}
                    className={`w-full flex items-center gap-3 px-4 py-3 rounded-lg text-left transition-all text-sm font-medium ${
                      activeView === item.view
                        ? "text-white shadow-md"
                        : "text-gray-600 hover:bg-gray-100 hover:text-gray-900"
                    } ${item.disabled ? "opacity-50 cursor-not-allowed" : ""}`}
                    style={{
                      backgroundColor: activeView === item.view ? "#2C3E50" : "transparent",
                    }}
                    aria-current={activeView === item.view ? "page" : undefined}
                    aria-disabled={item.disabled ? "true" : "false"}
                  >
                    {item.icon && <item.icon className="w-4 h-4" />}
                    <span>{item.label}</span>
                  </button>
                </li>
              ))}
            </ul>
          </div>
        )}
      </nav>

      <div className="border-t border-gray-200 p-4">
        <Button
          variant="ghost"
          size="sm"
          className="w-full justify-start text-gray-600 hover:text-gray-900"
          onClick={onLogout}
        >
          Logout
        </Button>
      </div>
    </aside>
  );
}

DashboardSidebar.propTypes = {
  navItems: PropTypes.arrayOf(
    PropTypes.shape({
      id: PropTypes.string.isRequired,
      label: PropTypes.string.isRequired,
      icon: PropTypes.elementType,
      view: PropTypes.string,
      href: PropTypes.string,
      section: PropTypes.oneOf(["primary", "support"]),
      disabled: PropTypes.bool,
      tourId: PropTypes.string,
    })
  ).isRequired,
  activeView: PropTypes.string.isRequired,
  onNavigate: PropTypes.func,
  onLogout: PropTypes.func,
  className: PropTypes.string,
};
