# Use Cases

This page explores real-world scenarios where Django Admin MCP shines.

## Content Management

### Blog Administration

A content team uses the agent to manage their Django-powered blog:

**Daily Tasks:**

- "Show me all articles pending review"
- "Publish the approved articles for today"
- "Update the featured article on the homepage"

**Content Creation:**

- "Create a new article with title 'Q4 Product Update'"
- "Add the 'announcements' and 'product' categories"
- "Set the publish date to tomorrow at 9 AM"

**Analytics Review:**

- "Which articles were published this week?"
- "Show me articles by author performance"
- "Find articles with no comments"

### Multi-Author Publishing

Managing a publication with multiple contributors:

```
User: Show me all draft articles waiting for review

Agent: [lists drafts ordered by creation date]

User: Assign article 42 to the "editors" review queue

Agent: [updates article with status="in_review"]

User: What articles has John submitted this month?

Agent: [lists articles filtered by author and date]
```

---

## E-commerce Operations

### Order Management

Customer service uses the agent to handle orders:

**Order Lookup:**

- "Find order #12345"
- "Show me orders from customer john@example.com"
- "List orders placed in the last 24 hours"

**Order Updates:**

- "Mark order #12345 as shipped"
- "Update tracking number to ABC123"
- "Refund order #12345 and add a note"

**Bulk Operations:**

- "Mark all orders from yesterday as processed"
- "Export orders pending shipment"

!!! note "Exports via admin actions"
    When an admin action returns a file (for example a CSV export), the
    `action_*` tool returns it as a structured file payload — UTF-8 text or
    base64-encoded content — capped at `MCP_ACTION_MAX_FILE_BYTES`
    (default 5 MiB). Larger files return an error instead.

### Inventory Management

```
User: Show me products with less than 10 items in stock

Agent: [lists products with low inventory]

User: Update product #567 stock to 100 units

Agent: [updates inventory count]

User: Which products haven't sold in 30 days?

Agent: [analyzes sales data]
```

---

## User Administration

### Account Management

IT teams manage user accounts:

**User Lookup:**

- "Find user with email alice@company.com"
- "Show me users created this week"
- "List inactive users (not logged in for 90 days)"

**Account Actions:**

- "Deactivate user #123"
- "Mark the marketing team's accounts as inactive"

### Access Control

These examples assume the `User` model is exposed through an admin that uses
`MCPAdminMixin`. The generated tools cover CRUD on user records — they do not
provide relation-traversal filters (such as "users with permission X") or a
permission-management tool, so permission changes themselves still happen in
Django admin.

```
User: Find the account for alice@company.com

Agent: [calls list_user with filters={"email": "alice@company.com"}]

User: Deactivate that account

Agent: [calls update_user with id=456, data={"is_active": false}]

User: Show me the change history for user #789

Agent: [calls history_user with id=789, displays audit log]
```

To answer a question like "who has billing access", the agent can list users
page by page and check each user's serialized fields client-side, but it
cannot filter by permission on the server.

---

## Data Analysis

### Report Generation

Analysts query data through natural language. The generated tools do not
perform aggregation (no sums, averages, or group-by) — the agent fetches
records with `list_*` and computes the numbers itself:

**Sales Reports:**

- "How many orders were placed last month?" — a `list_order` call with date
  filters returns `total_count` without fetching every row
- "What's the total revenue by category?" — the agent pages through orders
  with `list_order` and sums amounts per category client-side
- "Show me top 10 customers by order value" — the agent fetches order pages
  and ranks customers itself

**Content Analytics:**

- "Which articles got the most comments?" — the agent lists articles and
  counts related comments client-side
- "Show me publication frequency by author" — computed from paged
  `list_article` results

### Trend Analysis

```
User: Compare this month's signups to last month

Agent: [calls list_user twice with date_joined__gte/date_joined__lt bounds,
compares the total_count values]

User: Show me the growth trend for the past 6 months

Agent: [calls list_user once per month with date range filters, charts the
total_count values]
```

!!! note
    Each `list_*` page is capped at `MCP_MAX_LIST_LIMIT` (default 1000)
    items, so computing aggregates over large datasets requires paging with
    `offset` and may be slow. Prefer filtered `total_count` reads where a
    count is all you need.

---

## Automation Workflows

### Scheduled Tasks

Combine the agent with automation for scheduled operations:

**Daily Cleanup:**

- "Archive articles older than 2 years"
- "Delete unconfirmed user accounts older than 7 days"
- "Reset daily counters for all products"

**Weekly Reports:**

- "Generate summary of all changes this week"
- "List all new users and their registration sources"
- "Show me content published per author"

### Integration Pipelines

```
User: Export all premium users for the newsletter system

Agent: [lists premium users with email addresses]

User: Mark these 50 users as newsletter-synced

Agent: [bulk updates users with sync timestamp]
```

---

## Development & Testing

### Data Seeding

Developers populate test data:

```
User: Create 10 test articles with random titles

Agent: [bulk creates articles with generated data]

User: Create a test user with all permissions

Agent: [creates user, assigns permission groups]
```

### Debugging

Investigating issues in staging:

```
User: Show me the last 5 orders that failed processing

Agent: [lists orders with error status]

User: What changed on order #999 in the last hour?

Agent: [shows change history]

User: Who modified the product pricing yesterday?

Agent: [queries audit logs]
```

---

## Customer Support

### Ticket Resolution

Support teams resolve issues faster:

**Issue Investigation:**

- "Show me orders for customer email X"
- "What's the history of account #123?"
- "Find all refunds processed this week"

**Quick Fixes:**

- "Update shipping address for order #456"
- "Apply 10% discount to customer #789"
- "Reset user password and send notification"

### Escalation Workflow

```
User: Find all support tickets marked as urgent

Agent: [lists high-priority tickets]

User: Assign tickets 1, 2, 3 to the senior team

Agent: [bulk updates ticket assignments]

User: Add internal note to ticket #5

Agent: [updates ticket with internal comment]
```

---

## Best Practices

### Use Filters Effectively

Instead of fetching all records:

```
# Slow: fetch all, filter client-side
list_article(limit=1000)

# Fast: filter on the server
list_article(filters={"published": true, "author": 5})
```

Note that `limit` values above `MCP_MAX_LIST_LIMIT` (default 1000) are
silently clamped to that maximum — use `offset` to page through larger
result sets.

### Leverage Autocomplete

When creating records with foreign keys:

```
# Find the right author first
autocomplete_author(term="jane")
# Then create with the ID
create_article(data={"author_id": 5, ...})
```

### Use Bulk Operations

For multiple updates:

```
# Many round-trips: individual updates
update_article(id=1, data={"status": "archived"})
update_article(id=2, data={"status": "archived"})
update_article(id=3, data={"status": "archived"})

# One round-trip: bulk update
bulk_article(operation="update", items=[
  {"id": 1, "data": {"status": "archived"}},
  {"id": 2, "data": {"status": "archived"}},
  {"id": 3, "data": {"status": "archived"}}
])
```

The advantage is a single request instead of many — not fewer database
queries. On the server, bulk update still processes items one by one with
full form validation, a per-item lookup and save, and a per-item log entry.
Each item also commits independently: if item 2 fails, items 1 and 3 are
still applied (there is no cross-item rollback), and the response reports
per-item successes and errors.

### Check History for Auditing

Before making critical changes:

```
# Review what's been changed
history_article(id=42)
# Then make your update
update_article(id=42, data={...})
```

---

## Integration Tips

### Combine with Other MCP Servers

Django Admin MCP works alongside other MCP servers:

- **File System MCP** — Export data to files
- **Database MCP** — Run complex SQL queries
- **Git MCP** — Track configuration changes

### Build Custom Workflows

Chain operations for complex workflows:

1. Query for records matching criteria
2. Process/transform the data
3. Update records with results
4. Log the operation
