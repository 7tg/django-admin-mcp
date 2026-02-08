# 🎯 Use Cases

This page explores real-world scenarios where Django Admin MCP shines.

## 📰 Content Management

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

## 🛒 E-commerce Operations

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

## 👤 User Administration

### Account Management

IT teams manage user accounts:

**User Lookup:**

- "Find user with email alice@company.com"
- "Show me users created this week"
- "List inactive users (not logged in for 90 days)"

**Account Actions:**

- "Deactivate user #123"
- "Reset permissions for marketing team"
- "Add user to the 'premium' group"

### Access Control

```
User: Who has admin access to the billing section?

Agent: [queries users with specific permissions]

User: Remove billing access from user #456

Agent: [removes permissions]

User: Show me the change history for user #789

Agent: [displays audit log]
```

---

## 📊 Data Analysis

### Report Generation

Analysts query data through natural language:

**Sales Reports:**

- "How many orders were placed last month?"
- "What's the total revenue by category?"
- "Show me top 10 customers by order value"

**Content Analytics:**

- "Which articles got the most comments?"
- "Show me publication frequency by author"
- "Find trending topics this quarter"

### Trend Analysis

```
User: Compare this month's signups to last month

Agent: [queries user creation dates, calculates comparison]

User: Show me the growth trend for the past 6 months

Agent: [aggregates monthly data, presents trend]
```

---

## 🤖 Automation Workflows

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

## 🧪 Development & Testing

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

## 🎧 Customer Support

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

## 💡 Best Practices

### 🔍 Use Filters Effectively

Instead of fetching all records:

```
# Slow: fetch all, filter client-side
list_article(limit=1000)

# Fast: filter on the server
list_article(filters={"published": true, "author_id": 5})
```

### 🔎 Leverage Autocomplete

When creating records with foreign keys:

```
# Find the right author first
autocomplete_author(term="jane")
# Then create with the ID
create_article(data={"author_id": 5, ...})
```

### 📦 Use Bulk Operations

For multiple updates:

```
# Slow: individual updates
update_article(id=1, data={"status": "archived"})
update_article(id=2, data={"status": "archived"})
update_article(id=3, data={"status": "archived"})

# Fast: bulk update
bulk_article(operation="update", items=[
  {"id": 1, "data": {"status": "archived"}},
  {"id": 2, "data": {"status": "archived"}},
  {"id": 3, "data": {"status": "archived"}}
])
```

### 📜 Check History for Auditing

Before making critical changes:

```
# Review what's been changed
history_article(id=42)
# Then make your update
update_article(id=42, data={...})
```

---

## 🔗 Integration Tips

### 🤝 Combine with Other MCP Servers

Django Admin MCP works alongside other MCP servers:

- **File System MCP** — Export data to files
- **Database MCP** — Run complex SQL queries
- **Git MCP** — Track configuration changes

### 🔄 Build Custom Workflows

Chain operations for complex workflows:

1. Query for records matching criteria
2. Process/transform the data
3. Update records with results
4. Log the operation
