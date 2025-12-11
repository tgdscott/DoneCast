import React from "react";
import { Button } from "@/components/ui/button";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import {
  Headphones,
  Shield,
  LogOut,
  ArrowLeft,
} from "lucide-react";
import PropTypes from "prop-types";

/**
 * AdminSidebar - Renders the sidebar navigation for the admin dashboard
 * 
 * @param {Array} navigationItems - Array of nav items with {id, label, icon}
 * @param {string} activeTab - Currently active tab ID
 * @param {Function} setActiveTab - Callback to change active tab
 * @param {Function} logout - Callback to logout
 */
export default function AdminSidebar({ navigationItems, activeTab, setActiveTab, logout }) {
  return (
    <div className="w-64 bg-white border-r border-gray-200 flex flex-col">
      {/* Logo */}
      <div className="p-6 border-b border-gray-200">
        <div className="flex flex-col space-y-1">
          <img
            src="/assets/branding/logo-horizontal.png"
            alt="DoneCast"
            className="h-10 w-auto object-contain"
          />
          <p className="text-sm text-gray-500 pl-1">Admin Panel</p>
        </div>
      </div>

      {/* Navigation Menu */}
      <nav className="flex-1 p-4" role="navigation" aria-label="Admin side navigation">
        <ul className="space-y-2">
          {navigationItems.map((item) => (
            <li key={item.id}>
              <button
                onClick={() => setActiveTab(item.id)}
                className={`w-full flex items-center space-x-3 px-4 py-3 rounded-lg text-left transition-all ${activeTab === item.id
                    ? "text-white shadow-md"
                    : "text-gray-600 hover:bg-gray-100 hover:text-gray-800"
                  }`}
                style={{
                  backgroundColor: activeTab === item.id ? "#2C3E50" : "transparent",
                }}>
                <item.icon className="w-5 h-5" />
                <span className="font-medium">{item.label}</span>
              </button>
            </li>
          ))}
        </ul>
      </nav>

      {/* Admin Info */}
      <div className="p-4 border-t border-gray-200">
        <div className="flex items-center space-x-3 mb-3">
          <Avatar className="h-8 w-8">
            <AvatarFallback>
              <Shield className="w-4 h-4" />
            </AvatarFallback>
          </Avatar>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium text-gray-800">Admin User</p>
            <p className="text-xs text-gray-500">Platform Administrator</p>
          </div>
        </div>
        <Button
          onClick={() => window.location.href = '/dashboard?view=user'}
          variant="ghost"
          size="sm"
          className="w-full justify-start text-gray-600 mb-2"
        >
          <ArrowLeft className="w-4 h-4 mr-2" />
          Back to Dashboard
        </Button>
        <Button onClick={logout} variant="ghost" size="sm" className="w-full justify-start text-gray-600">
          <LogOut className="w-4 h-4 mr-2" />
          Logout
        </Button>
      </div>
    </div>
  );
}

AdminSidebar.propTypes = {
  navigationItems: PropTypes.arrayOf(
    PropTypes.shape({
      id: PropTypes.string.isRequired,
      label: PropTypes.string.isRequired,
      icon: PropTypes.elementType.isRequired,
    })
  ).isRequired,
  activeTab: PropTypes.string.isRequired,
  setActiveTab: PropTypes.func.isRequired,
  logout: PropTypes.func.isRequired,
};
