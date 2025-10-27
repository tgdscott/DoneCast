# Podcast Plus Plus - Monitoring & Analytics Setup

This directory contains comprehensive monitoring configurations for your Podcast Plus Plus platform, designed to help with bug detection, performance optimization, and system health monitoring.

## 📁 Files Overview

- **`log_analytics_queries.kql`** - Complete collection of KQL queries for all monitoring scenarios
- **`log_analytics_alerts.kql`** - Alert rules and thresholds for proactive monitoring  
- **`workbook_template.json`** - Azure Monitor Workbook template (ready to import)
- **`monitoring_setup_guide.md`** - Step-by-step implementation instructions

## 🎯 Key Monitoring Areas Covered

### 1. **Error Detection & Bug Analysis**
- Critical error tracking with automatic categorization
- Episode processing failure analysis
- Authentication and user experience issues
- Detailed error breakdowns by component

### 2. **Performance Monitoring**
- API response time analysis with P95/P99 percentiles
- Database query performance tracking
- Memory and resource utilization patterns
- Endpoint-specific performance metrics

### 3. **Business Logic Health**
- Transcription service health (AssemblyAI vs Auphonic)
- Episode assembly pipeline monitoring
- User tier distribution and usage patterns
- Revenue-impacting event tracking

### 4. **Infrastructure Health**
- Cloud Run instance performance
- GCS upload/download success rates
- Database connection pool health
- Queue processing and backlog monitoring

### 5. **User Experience Tracking**
- Registration and onboarding funnel analysis
- Episode creation success rates
- Feature usage trends and adoption
- Content processing volume metrics

### 6. **Security & Abuse Detection**
- Suspicious activity pattern recognition
- Failed login attempt monitoring
- Rate limiting and abuse prevention
- IP-based threat detection

## 🚀 Quick Start

### 1. Deploy the Dashboard
```bash
# 1. Go to Azure Portal → Monitor → Workbooks → + New
# 2. Click "Advanced Editor" (</> icon)
# 3. Copy content from workbook_template.json
# 4. Replace YOUR_SUBSCRIPTION_ID and YOUR_RESOURCE_GROUP
# 5. Save as "Podcast Plus Plus Operations Dashboard"
```

### 2. Set Up Critical Alerts
```bash
# Use queries from log_analytics_alerts.kql to create:
# - High error rate alerts (5 minute window)
# - Episode processing failure spikes
# - GCS operation failures
# - Authentication crisis detection
```

### 3. Test Core Queries
```kql
# Start with this basic health check:
traces
| where timestamp > ago(1h)
| where cloud_RunRevision_s contains "podcast-api"
| summarize 
    TotalEvents = count(),
    Errors = countif(severityLevel >= 3),
    ErrorRate = countif(severityLevel >= 3) * 100.0 / count()
```

## 📊 Dashboard Features

- **🎯 Executive KPI Tiles** - System health at a glance
- **📈 Real-time Charts** - Episode processing pipeline visualization
- **🔍 Error Analysis** - Categorized error breakdown with drill-down
- **👥 User Analytics** - Tier-based usage patterns and activity
- **🎤 Service Health** - Transcription service performance comparison
- **⚡ Performance Metrics** - API latency and throughput analysis

## 🔔 Recommended Alert Setup

### Critical (P1) - Immediate Response
- Service down/unavailable
- Database connection failures
- GCS storage issues
- High error rates (>15% in 5 minutes)

### High (P2) - Business Hours Priority  
- Episode processing failures
- Payment/billing issues
- Authentication problems
- Performance degradation

### Medium (P3) - Standard Monitoring
- Elevated warning levels
- Feature-specific issues
- Onboarding funnel problems

### Low (P4) - Informational
- Usage trend changes
- Daily/weekly summaries
- Capacity planning metrics

## 🛠 Customization Guide

### Adjust for Your Environment:
1. **Service Names**: Update `cloud_RunRevision_s contains "podcast-api"` to match your deployment
2. **Time Windows**: Modify alert time ranges based on your traffic patterns  
3. **Thresholds**: Adjust error rate and performance thresholds based on baseline metrics
4. **Categories**: Add new error categories as you identify patterns

### Performance Optimization:
- Use time range parameters to avoid expensive queries
- Pre-aggregate common metrics for faster loading
- Archive old data to control Log Analytics costs
- Use sampling for high-volume trace analysis

## 🔧 Troubleshooting Common Issues

### Dashboard Not Loading:
- Verify Log Analytics workspace permissions
- Check that Cloud Run logging is properly configured
- Ensure `cloud_RunRevision_s` field exists in your logs

### Missing Data in Charts:
- Confirm log retention settings
- Verify service naming conventions
- Check time zone configurations

### High Query Costs:
- Implement query result caching
- Use shorter time windows for real-time dashboards  
- Archive historical data appropriately

## 📈 Next Steps

1. **Deploy Core Monitoring** - Start with basic health dashboard
2. **Set Up Critical Alerts** - Configure immediate notification for P1 issues
3. **Baseline Performance** - Run for 1-2 weeks to establish normal patterns
4. **Refine Thresholds** - Adjust alert sensitivity based on actual traffic
5. **Expand Coverage** - Add business-specific metrics and custom alerts
6. **Automate Response** - Integrate with incident management tools

## 🤝 Support & Maintenance

- **Review Monthly**: Update queries and thresholds based on platform changes
- **Validate Alerts**: Test alert channels and escalation procedures  
- **Optimize Costs**: Monitor Log Analytics usage and optimize expensive queries
- **Document Incidents**: Use monitoring data to improve future alerting

---

**Ready to deploy?** Start with the basic health dashboard and core alerts, then expand based on your operational needs. These queries are designed to scale with your platform and provide actionable insights for maintaining system reliability.