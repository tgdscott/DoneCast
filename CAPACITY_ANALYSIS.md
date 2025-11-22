# System Capacity Analysis - Podcast Plus Plus

**Date:** December 2024  
**Purpose:** Estimate simultaneous user capacity

---

## Current Infrastructure

### Cloud Run API Service
- **CPU:** 1 core per instance
- **Memory:** 2GB per instance
- **Timeout:** 3600s (1 hour)
- **Concurrency:** ~80 requests per instance (Cloud Run default)
- **Scaling:** Auto-scales based on request volume
- **Min Instances:** 0 (cold starts possible)
- **Max Instances:** Not explicitly set (defaults to Cloud Run limits)

### Database (Cloud SQL PostgreSQL)
- **Max Connections:** 200 total
- **Reserved:** 3 (superuser)
- **Available:** 197 connections
- **Pool Size:** 10 base + 10 overflow = 20 per instance
- **Max Instances Supported:** ~10 instances (197 / 20 = 9.85)

### Worker Service
- **CPU:** 1 core per instance
- **Memory:** 2GB per instance
- **Timeout:** 3600s (1 hour)
- **Purpose:** Long-running episode assembly tasks

---

## Capacity Calculation

### Method 1: Database Connection Limit (Bottleneck)

**Formula:**
```
Max Concurrent Users = (Available DB Connections / Connections per User) × Instances
```

**Assumptions:**
- Each API instance uses 20 DB connections (pool size)
- Average user request holds DB connection for ~200ms
- Peak concurrency: 80 requests per instance

**Calculation:**
- **Max API Instances:** 197 / 20 = **~10 instances**
- **Concurrent Requests:** 10 instances × 80 requests = **800 concurrent requests**
- **With 200ms avg DB time:** 800 × (1000ms / 200ms) = **~4,000 requests/second capacity**

**Realistic User Capacity:**
- Average user makes 1 request every 5 seconds during active use
- **4,000 req/s ÷ 0.2 req/s per user = ~20,000 active users**

### Method 2: Request Processing Capacity

**Assumptions:**
- Average request duration: 200ms (simple API calls)
- Peak request duration: 5s (complex operations like AI generation)
- Cloud Run concurrency: 80 requests per instance

**Simple Requests (80% of traffic):**
- 10 instances × 80 concurrency = 800 concurrent simple requests
- At 200ms each: 800 × (1000ms / 200ms) = **4,000 req/s**

**Complex Requests (20% of traffic):**
- 10 instances × 80 concurrency = 800 concurrent complex requests
- At 5s each: 800 × (1000ms / 5000ms) = **160 req/s**

**Mixed Workload:**
- Weighted average: (4,000 × 0.8) + (160 × 0.2) = **3,232 req/s**
- **User capacity:** 3,232 ÷ 0.2 = **~16,000 active users**

### Method 3: External API Rate Limits (Bottleneck)

**Gemini API:**
- Free tier: 15 RPM (requests per minute)
- Paid tier: Higher limits
- **Bottleneck:** If all users generate AI content simultaneously

**AssemblyAI:**
- Pay-as-you-go pricing
- No explicit rate limits mentioned
- **Bottleneck:** Cost, not rate limits

**Estimated Capacity:**
- If 10% of requests use Gemini: 3,232 × 0.1 = 323 req/s
- Gemini free tier: 15 RPM = 0.25 req/s per API key
- **Would need:** 323 / 0.25 = **1,292 API keys** (unrealistic)

**Reality Check:**
- Circuit breakers prevent cascading failures
- Rate limiting on frontend reduces simultaneous AI requests
- **Realistic capacity:** Limited by Gemini rate limits, not infrastructure

---

## Realistic Capacity Estimate

### Conservative Estimate (Current Configuration)

**Assumptions:**
- Database connection pool is the primary bottleneck
- 10 API instances maximum
- 80 concurrent requests per instance
- Average request duration: 500ms (mixed workload)
- Users make 1 request every 5 seconds during active use

**Calculation:**
- **Concurrent Requests:** 10 × 80 = 800
- **Request Throughput:** 800 × (1000ms / 500ms) = **1,600 req/s**
- **Active Users:** 1,600 ÷ 0.2 = **~8,000 simultaneous active users**

### Optimistic Estimate (With Optimizations)

**If we optimize:**
- Increase DB pool to 20+10 = 30 per instance
- Support 6-7 instances (197 / 30 = 6.5)
- Reduce average request time to 300ms
- Increase concurrency to 100 per instance

**Calculation:**
- **Concurrent Requests:** 7 × 100 = 700
- **Request Throughput:** 700 × (1000ms / 300ms) = **2,333 req/s**
- **Active Users:** 2,333 ÷ 0.2 = **~11,600 simultaneous active users**

### Peak Capacity (Burst Traffic)

**During peak events:**
- All 10 instances active
- 80 concurrency per instance
- Short requests only (200ms average)

**Calculation:**
- **Concurrent Requests:** 10 × 80 = 800
- **Request Throughput:** 800 × (1000ms / 200ms) = **4,000 req/s**
- **Peak Users:** 4,000 ÷ 0.2 = **~20,000 simultaneous users**

---

## Bottlenecks & Limitations

### 1. Database Connection Pool (PRIMARY BOTTLENECK)
- **Current:** 197 available connections
- **Per Instance:** 20 connections
- **Max Instances:** ~10
- **Solution:** Increase DB max_connections or optimize pool usage

### 2. External API Rate Limits
- **Gemini:** 15 RPM free tier (major bottleneck)
- **AssemblyAI:** Pay-as-you-go (cost concern)
- **Solution:** Circuit breakers, caching, rate limiting

### 3. Long-Running Operations
- **Episode Assembly:** Can take 5-30 minutes
- **Transcription:** Can take 2-10 minutes
- **Impact:** Blocks worker instances, not API instances
- **Solution:** Async processing (already implemented)

### 4. Memory Constraints
- **Current:** 2GB per instance
- **Audio Processing:** Can use 1-2GB per operation
- **Impact:** Limits concurrent audio operations
- **Solution:** Increase memory or offload to worker service

---

## Scaling Recommendations

### Immediate (No Code Changes)

1. **Increase Database Connections**
   - Current: 200 max
   - Recommended: 500 max
   - **Impact:** Supports ~25 instances instead of 10

2. **Increase Pool Size**
   - Current: 10+10 = 20 per instance
   - Recommended: 20+10 = 30 per instance
   - **Impact:** Better connection utilization

3. **Set Min Instances**
   - Current: 0 (cold starts)
   - Recommended: 2-3 instances
   - **Impact:** Eliminates cold start delays

### Short-Term (Configuration Changes)

1. **Increase Cloud Run Resources**
   - CPU: 1 → 2 cores
   - Memory: 2GB → 4GB
   - **Impact:** Handles more concurrent requests per instance

2. **Increase Concurrency**
   - Current: 80 (default)
   - Recommended: 100-120
   - **Impact:** More requests per instance

3. **Add Load Balancing**
   - Multiple regions
   - **Impact:** Better geographic distribution

### Long-Term (Architecture Changes)

1. **Read Replicas**
   - Separate read/write databases
   - **Impact:** 2-3x read capacity

2. **Caching Layer**
   - Redis for frequently accessed data
   - **Impact:** Reduces database load significantly

3. **CDN for Static Assets**
   - Already implemented for media files
   - **Impact:** Reduces API load

---

## Real-World Capacity Estimate

### Conservative (Safe for Production)

**~5,000-8,000 simultaneous active users**

**Reasoning:**
- Database connection pool limits to ~10 instances
- 10 instances × 80 concurrency = 800 concurrent requests
- Average request: 500ms → 1,600 req/s
- Users make ~0.2 req/s → 8,000 active users

### Realistic (With Optimizations)

**~10,000-15,000 simultaneous active users**

**With:**
- Increased DB connections (500 max)
- Optimized pool sizes (30 per instance)
- Better request handling (300ms average)
- Increased concurrency (100 per instance)

### Peak Capacity (Burst)

**~20,000+ simultaneous users**

**During:**
- Short-duration requests only
- All instances active
- Optimized configuration

---

## Monitoring & Alerts

### Key Metrics to Watch

1. **Database Connection Pool Utilization**
   - Alert when > 80% utilized
   - Current: 197 connections max

2. **Request Latency**
   - P95 should be < 2s
   - P99 should be < 5s

3. **Error Rate**
   - Should be < 0.1%
   - Watch for 503 errors (service unavailable)

4. **Instance Count**
   - Monitor scaling behavior
   - Alert if max instances reached

### Capacity Warnings

**Yellow Alert (70% capacity):**
- DB pool > 140 connections
- Instance count > 7
- P95 latency > 1.5s

**Red Alert (90% capacity):**
- DB pool > 180 connections
- Instance count > 9
- P95 latency > 2s
- Error rate > 0.5%

---

## Conclusion

### Current Capacity: **~5,000-8,000 simultaneous active users**

**Primary Bottleneck:** Database connection pool (197 connections)

**Recommendations:**
1. ✅ **Immediate:** Increase DB max_connections to 500
2. ✅ **Short-term:** Optimize pool sizes and increase Cloud Run resources
3. ✅ **Long-term:** Add read replicas and caching layer

**With Optimizations:** **~10,000-15,000 simultaneous active users**

**Peak Capacity:** **~20,000+ simultaneous users** (burst traffic)

---

*Analysis based on current infrastructure configuration and typical usage patterns*


