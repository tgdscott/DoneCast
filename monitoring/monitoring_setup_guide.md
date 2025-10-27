# Podcast Plus Plus - Monitoring Implementation Guide

## 🎯 Overview

This guide walks you through implementing comprehensive monitoring for your Podcast Plus Plus platform using Azure Log Analytics. The monitoring system is designed to catch bugs early, optimize performance, and ensure system reliability.

## 📋 Prerequisites

- Azure Log Analytics workspace connected to Cloud Run
- Appropriate permissions for creating queries, alerts, and dashboards
- Basic familiarity with KQL (Kusto Query Language)

## 🚀 Implementation Steps

### Step 1: Verify Log Analytics Integration

First, confirm your Cloud Run services are properly sending logs to Log Analytics:

```kql
// Test query - should return recent logs
traces
| where timestamp > ago(1h)
| where cloud_RunRevision_s contains "podcast"
| limit 10
```

**Expected result**: Recent log entries from your podcast-api service

**If no results**: 
- Check Cloud Run logging configuration
- Verify Log Analytics workspace connection
- Confirm service name matches your deployment

### Step 2: Deploy Core Health Dashboard

1. **Go to Azure Portal** → Monitor → Workbooks → + New
2. **Click "Advanced Editor"** (</> icon in top toolbar)  
3. **Copy and paste** the complete JSON from `workbook_template.json`
4. **Update placeholders**:
   - Replace `YOUR_SUBSCRIPTION_ID` with your Azure subscription ID
   - Replace `YOUR_RESOURCE_GROUP` with your resource group name
5. **Save as**: "Podcast Plus Plus Operations Dashboard"

### Step 3: Set Up Critical Alerts

Create these essential alerts using queries from `log_analytics_alerts.kql`:

#### Alert 1: High Error Rate
```kql
traces
| where timestamp > ago(5m)
| where cloud_RunRevision_s contains "podcast-api"
| where severityLevel >= 3
| summarize ErrorCount = count()
| where ErrorCount > 10
```
- **Threshold**: >10 errors in 5 minutes
- **Severity**: Critical (P1)
- **Notification**: Immediate

#### Alert 2: Episode Processing Failures
```kql
traces
| where timestamp > ago(10m)
| where cloud_RunRevision_s contains "podcast-api"
| where message contains "assembly" and (message contains "failed" or message contains "ERROR")
| summarize FailureCount = count()
| where FailureCount > 3
```
- **Threshold**: >3 assembly failures in 10 minutes
- **Severity**: High (P2)
- **Notification**: 5 minute delay

#### Alert 3: API Performance Degradation
```kql
requests
| where timestamp > ago(5m)
| where cloud_RunRevision_s contains "podcast-api"
| where duration > 50000000  // 5+ seconds
| summarize SlowRequests = count()
| where SlowRequests > 5
```
- **Threshold**: >5 slow requests (>5s) in 5 minutes
- **Severity**: High (P2)
- **Notification**: Business hours priority

### Step 4: Configure Notification Channels

Set up notification channels for different alert severities:

1. **Critical (P1)**: 
   - SMS for on-call engineer
   - Email to ops team
   - Slack/Teams for immediate visibility

2. **High (P2)**:
   - Email to development team
   - Slack channel notification
   - 5-minute delay to avoid noise

3. **Medium (P3)**:
   - Email digest (hourly)
   - Dashboard alerts only
   - Normal escalation

### Step 5: Baseline Performance Metrics

Run these queries to establish baseline performance:

#### API Response Time Baseline
```kql
requests
| where timestamp > ago(7d)
| where cloud_RunRevision_s contains "podcast-api"
| extend LatencyMs = duration / 10000.0
| summarize 
    AvgLatency = avg(LatencyMs),
    P95Latency = percentile(LatencyMs, 95),
    P99Latency = percentile(LatencyMs, 99)
by bin(timestamp, 1h)
| render timechart
```

#### Error Rate Trends
```kql
traces
| where timestamp > ago(7d)
| where cloud_RunRevision_s contains "podcast-api"
| summarize 
    TotalLogs = count(),
    ErrorRate = countif(severityLevel >= 3) * 100.0 / count()
by bin(timestamp, 1h)
| render timechart
```

#### Episode Processing Success Rate
```kql
traces
| where timestamp > ago(7d)
| where cloud_RunRevision_s contains "podcast-api"
| where message contains "assembly"
| extend Status = case(
    message contains "complete", "Success",
    message contains "failed", "Failed",
    "In Progress"
)
| summarize Count = count() by Status, bin(timestamp, 4h)
| render columnchart
```

## 🎛 Dashboard Configuration

### Panel 1: Executive Summary (KPI Tiles)
- Total events (last hour)
- Error count and error rate
- Critical alerts active
- System availability percentage

### Panel 2: Episode Processing Health
- Processing pipeline stages
- Success/failure rates by stage
- Processing time trends
- Queue backlog monitoring

### Panel 3: API Performance Metrics
- Request volume by endpoint
- Response time percentiles
- Error rates by endpoint
- Geographic distribution (if available)

### Panel 4: Business Metrics
- User tier activity distribution
- Feature usage patterns
- Content processing volume
- Revenue-impacting events

### Panel 5: Infrastructure Health
- Memory and CPU utilization
- Database connection health
- GCS operation success rates
- Container restart frequency

## 🔧 Customization Examples

### Adding Custom Error Categories

Modify the error categorization logic:

```kql
| extend ErrorCategory = case(
    message contains "assembly", "🔧 Episode Assembly", 
    message contains "transcription", "🎤 Transcription",
    message contains "GCS", "☁️ Cloud Storage",
    message contains "database", "🗄️ Database",
    message contains "auth", "🔐 Authentication",
    message contains "billing", "💳 Billing",
    message contains "your_new_feature", "🆕 Your Feature",  // Add this line
    "❓ Other"
)
```

### Environment-Specific Filtering

For staging vs production monitoring:

```kql
traces
| where timestamp > ago(1h)
| where cloud_RunRevision_s contains "podcast-api"
| where customDimensions.environment == "production"  // Add environment filter
| summarize ErrorCount = count() by severityLevel
```

### User-Specific Issue Tracking

Track issues for specific users or tiers:

```kql
traces
| where timestamp > ago(24h)
| where cloud_RunRevision_s contains "podcast-api"
| where severityLevel >= 3
| extend UserId = extract(@"user[_\s]+(\d+)", 1, message)
| extend UserTier = extract(@"tier[_\s]+(\w+)", 1, message)
| summarize 
    IssueCount = count(),
    SampleMessage = take_any(message)
by UserId, UserTier
| where IssueCount > 5  // Users with >5 errors
| order by IssueCount desc
```

## 🚨 Alert Tuning Guidelines

### Initial Alert Thresholds (Conservative)

Start with higher thresholds to avoid alert fatigue:

- **Error Rate**: >20% (vs 15% in production)
- **Response Time**: >10s (vs 5s in production)  
- **Failure Count**: >10 (vs 5 in production)

### Progressive Tuning Process

1. **Week 1-2**: Monitor false positive rate
2. **Week 3-4**: Lower thresholds by 25% if stable
3. **Month 2**: Fine-tune based on actual incident patterns
4. **Ongoing**: Monthly review and adjustment

### Alert Fatigue Prevention

- **Group related alerts** (e.g., cascade failures)
- **Use progressive escalation** (warning → error → critical)
- **Implement auto-resolution** (30-60 minute timeouts)
- **Schedule maintenance windows** (disable alerts during deployments)

## 📊 Query Optimization Tips

### Performance Best Practices

1. **Use time ranges wisely**:
   ```kql
   // Good - specific time range
   | where timestamp > ago(1h)
   
   // Bad - open-ended query
   | where timestamp > ago(30d)
   ```

2. **Filter early in the pipeline**:
   ```kql
   // Good - filter first
   traces
   | where cloud_RunRevision_s contains "podcast-api"
   | where severityLevel >= 3
   | summarize count()
   
   // Bad - filter after processing
   traces
   | summarize count() by cloud_RunRevision_s, severityLevel
   | where cloud_RunRevision_s contains "podcast-api" and severityLevel >= 3
   ```

3. **Use sampling for high-volume data**:
   ```kql
   traces
   | where timestamp > ago(24h)
   | sample 10000  // Limit to 10k rows for analysis
   | summarize count() by bin(timestamp, 1h)
   ```

### Cost Control Strategies

- **Cache common query results** (use workbook parameters)
- **Limit dashboard refresh rates** (5-10 minutes vs real-time)
- **Archive old data** (retain 30-90 days in hot storage)
- **Use log retention policies** (cheaper cold storage for historical data)

## 🔍 Troubleshooting Common Issues

### Dashboard Shows No Data

**Problem**: Workbook panels are empty
**Solutions**:
1. Check time range parameters (may be too narrow)
2. Verify service name filtering
3. Confirm Log Analytics workspace permissions
4. Test individual queries in Log Analytics

### Alerts Not Triggering

**Problem**: Known issues not generating alerts  
**Solutions**:
1. Verify alert query logic with recent data
2. Check notification channel configuration
3. Confirm alert is enabled and not in maintenance mode
4. Review alert history for suppression rules

### High Log Analytics Costs

**Problem**: Unexpected billing increases
**Solutions**:
1. Review query complexity and frequency
2. Implement data sampling for high-volume analysis
3. Adjust log retention policies
4. Archive historical data to cheaper storage

### Performance Issues

**Problem**: Dashboards loading slowly
**Solutions**:
1. Optimize query performance (add filters, reduce time ranges)
2. Use query result caching
3. Reduce dashboard refresh frequency
4. Split complex dashboards into focused views

## 📈 Advanced Features

### Automated Incident Response

Integrate with Azure Logic Apps for automated responses:

```json
{
  "trigger": "High error rate alert",
  "actions": [
    "Create incident ticket",
    "Scale up Cloud Run instances", 
    "Send Slack notification with runbook link",
    "Trigger diagnostic data collection"
  ]
}
```

### Machine Learning Anomaly Detection

Use Azure ML for advanced pattern recognition:

```kql
traces
| where timestamp > ago(30d)
| make-series ErrorRate = countif(severityLevel >= 3) * 100.0 / count() 
  on timestamp step 1h
| extend AnomalyScore = series_decompose_anomalies(ErrorRate, 1.5, 7, 'linefit')
| render anomalychart
```

### Cross-Service Correlation

Monitor dependencies and cascading failures:

```kql
traces
| where timestamp > ago(1h)
| where cloud_RunRevision_s in ("podcast-api", "podcast-worker", "podcast-frontend")
| where severityLevel >= 3
| summarize ErrorCount = count() by cloud_RunRevision_s, bin(timestamp, 5m)
| render timechart
```

## 🎓 Learning Resources

### KQL Learning Path
1. [KQL Quick Reference](https://docs.microsoft.com/azure/data-explorer/kql-quick-reference)
2. [Log Analytics Tutorial](https://docs.microsoft.com/azure/azure-monitor/log-query/get-started-queries)
3. [Advanced KQL Patterns](https://docs.microsoft.com/azure/data-explorer/kusto/query/tutorials/learn-common-operators)

### Azure Monitor Best Practices
1. [Monitoring Best Practices](https://docs.microsoft.com/azure/azure-monitor/best-practices)
2. [Alert Design Guidelines](https://docs.microsoft.com/azure/azure-monitor/platform/alerts-best-practices)
3. [Workbook Design Patterns](https://docs.microsoft.com/azure/azure-monitor/platform/workbooks-overview)

## ✅ Success Metrics

After implementing this monitoring setup, you should achieve:

- **🎯 99.9% uptime visibility** - Know about issues before users report them
- **⚡ <5 minute detection time** - Critical issues identified quickly
- **📊 <15% false positive rate** - Actionable alerts without noise
- **🔧 50% faster incident resolution** - Better context and faster diagnosis
- **📈 Proactive optimization** - Performance trends and capacity planning

## 🔄 Maintenance Schedule

### Daily (Automated)
- Review critical alert status
- Check dashboard health
- Validate key metrics trending

### Weekly (15 minutes)
- Review alert accuracy and tune thresholds  
- Check for new error patterns
- Validate monitoring coverage for new features

### Monthly (1 hour)
- Analyze monitoring costs and optimize queries
- Review incident patterns and improve alerting
- Update documentation and runbooks
- Plan monitoring enhancements

---

**🚀 Ready to deploy?** Start with Step 1 to verify your logging setup, then work through each step systematically. This monitoring foundation will provide the visibility you need to maintain a reliable, high-performance platform.