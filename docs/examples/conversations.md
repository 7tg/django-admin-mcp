# Example Conversations

This page shows real-world example conversations between users and Claude using Django Admin MCP.

## Model Discovery

### Exploring Available Models

```
User: What models are available in Django admin?

Claude: [calls find_models]

I found the following models available through Django Admin MCP:

**Fully Exposed (with CRUD tools):**
- article - 12 tools available
- category - 12 tools available
- comment - 12 tools available

**Discoverable Only:**
- author - no direct tools, but visible in find_models
- user - no direct tools

Would you like me to describe any of these models in detail?
```

### Understanding Model Structure

```
User: What fields does article have?

Claude: [calls describe_article]

The Article model has the following fields:

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| id | AutoField | No | Primary key (read-only) |
| title | CharField | Yes | Max 200 characters |
| slug | SlugField | Yes | URL-friendly identifier |
| content | TextField | No | Article body |
| author | ForeignKey | Yes | Links to Author model |
| categories | ManyToMany | No | Links to Category model |
| published | Boolean | No | Default: false |
| created_at | DateTime | No | Auto-set on creation |
| updated_at | DateTime | No | Auto-set on update |

The admin is configured with:
- Search fields: title, content
- Ordering: -created_at (newest first)
- Read-only fields: created_at, updated_at
```

---

## CRUD Operations

### Listing Records

```
User: Show me the latest 10 articles

Claude: [calls list_article with limit=10]

Here are the 10 most recent articles:

| ID | Title | Author | Published | Created |
|----|-------|--------|-----------|---------|
| 42 | Getting Started with Django | Jane Doe | Yes | Jan 15 |
| 41 | Python Best Practices | John Smith | Yes | Jan 14 |
| 40 | REST API Design | Jane Doe | No | Jan 13 |
| 39 | Database Optimization | Admin | Yes | Jan 12 |
| ... | ... | ... | ... | ... |

Showing 10 of 42 total articles.
```

### Filtering and Searching

```
User: Find all published articles about Django

Claude: [calls list_article with search="Django", filters={"published": true}]

Found 5 published articles matching "Django":

1. **Getting Started with Django** (ID: 42)
   Author: Jane Doe | Created: Jan 15, 2024

2. **Django REST Framework Tutorial** (ID: 35)
   Author: John Smith | Created: Jan 8, 2024

3. **Django Testing Best Practices** (ID: 28)
   Author: Jane Doe | Created: Dec 20, 2023

...
```

### Creating Records

```
User: Create a new article titled "Introduction to Python"

Claude: I'll create that article. Who should be the author?

User: Jane Doe

Claude: [calls autocomplete_author with search="Jane Doe"]
[calls create_article with data={"title": "Introduction to Python", "author_id": 5}]

Created article #43: "Introduction to Python"
- Author: Jane Doe
- Published: No (draft)
- Created: Just now

Would you like me to add content or publish it?
```

### Updating Records

```
User: Update article 43 with this content: "Python is a versatile programming
language..." and mark it as published

Claude: [calls update_article with id=43, data={"content": "Python is a versatile
programming language...", "published": true}]

Updated article #43:
- Content added (126 characters)
- Status changed to Published

The article is now live!
```

### Deleting Records

```
User: Delete article 43

Claude: Are you sure you want to delete article #43 "Introduction to Python"?
This action cannot be undone.

User: Yes, delete it

Claude: [calls delete_article with id=43]

Deleted article #43 "Introduction to Python".
```

---

## Admin Actions

### Listing Available Actions

```
User: What actions can I perform on articles?

Claude: [calls actions_article]

Available actions for articles:

1. **delete_selected** - Delete selected articles
2. **mark_as_published** - Mark selected articles as published
3. **mark_as_draft** - Mark selected articles as draft
4. **export_to_csv** - Export selected articles to CSV

Which action would you like to perform?
```

### Executing Actions

```
User: Mark articles 1, 2, and 3 as published

Claude: [calls action_article with action="mark_as_published", ids=[1, 2, 3]]

Marked 3 articles as published:
- Article #1: "Getting Started"
- Article #2: "Advanced Topics"
- Article #3: "Best Practices"

All three articles are now live.
```

---

## Bulk Operations

### Bulk Update

```
User: Set status to "archived" for articles 10 through 15

Claude: [calls bulk_article with operation="update", ids=[10, 11, 12, 13, 14, 15],
data={"status": "archived"}]

Updated 6 articles:
- Articles 10-15 now have status "archived"

All changes have been saved.
```

### Bulk Delete

```
User: Delete all draft articles from 2023

Claude: [calls list_article with filters={"published": false,
"created_at__year": 2023}]

Found 12 draft articles from 2023. Here they are:
- #15: "Untitled Draft" (Jan 2023)
- #18: "Old Tutorial" (Mar 2023)
...

Do you want me to delete all 12 articles?

User: Yes, delete them all

Claude: [calls bulk_article with operation="delete", ids=[15, 18, ...]]

Deleted 12 draft articles from 2023.
```

---

## Exploring Relationships

### Getting Related Objects

```
User: Show me all comments on article 42

Claude: [calls related_article with id=42, relation="comments"]

Article #42 "Getting Started with Django" has 8 comments:

1. **Great article!** - user123 (Jan 15, 10:30 AM)
2. **Very helpful tutorial** - django_fan (Jan 15, 11:00 AM)
3. **Could you add more examples?** - newbie (Jan 15, 2:00 PM)
...

Showing 8 comments total.
```

### Viewing Change History

```
User: What changes were made to article 42?

Claude: [calls history_article with id=42]

Change history for article #42:

| Date | User | Action | Changes |
|------|------|--------|---------|
| Jan 15, 2:30 PM | admin | Change | Changed title and content |
| Jan 15, 10:00 AM | admin | Add | Created article |

The article was created on Jan 15 and modified once.
```

---

## Complex Workflows

### Finding and Updating Multiple Related Records

```
User: Find all articles by Jane Doe and add the "featured" category to them

Claude: [calls list_article with filters={"author__name": "Jane Doe"}]
[calls autocomplete_category with search="featured"]

Found 15 articles by Jane Doe and the "featured" category (ID: 7).

I'll update each article to add this category...

[calls update_article for each article]

Added "featured" category to 15 articles by Jane Doe:
- Article #42: "Getting Started with Django"
- Article #35: "REST API Design"
- Article #28: "Testing Best Practices"
...

All articles are now featured!
```

### Audit and Cleanup

```
User: Show me articles that haven't been updated in the last 30 days

Claude: [calls list_article with filters={"updated_at__lt": "2023-12-15"}]

Found 23 articles not updated in the last 30 days:

**Oldest (over 6 months):**
- #5: "Legacy Tutorial" - Last updated: Jun 2023
- #8: "Old Documentation" - Last updated: Jul 2023

**1-6 months old:**
- #12: "Archived Content" - Last updated: Sep 2023
...

Would you like me to archive these or take another action?
```

---

## Error Handling Examples

### Permission Denied

```
User: Delete all articles

Claude: [calls bulk_article with operation="delete", ids=[...]]

I can't delete articles - the API token doesn't have delete permission.

To fix this:
1. Go to Django admin
2. Edit the MCP token
3. Add "blog.delete_article" permission

Or use a different token with delete access.
```

### Validation Error

```
User: Create an article without a title

Claude: [calls create_article with data={"content": "Some content"}]

Couldn't create the article - validation failed:

- **title**: This field is required.
- **author_id**: This field is required.

Please provide a title and author to create the article.
```
