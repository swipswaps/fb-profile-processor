# AI Studio Prompt: Facebook Profile URL Processor & Data Extractor

## Objective
Create a production-ready React application that processes Facebook Marketplace profile URLs, extracts user details, and stores them in a structured format with real-time progress tracking and export capabilities.

## Core Requirements

### 1. URL Processing Pipeline
- Accept input: text file containing Facebook Marketplace profile URLs (format: `https://www.facebook.com/marketplace/profile/{ID}/...`)
- Transform URLs to clean format: `https://www.facebook.com/{ID}`
- Support batch processing with progress indicators
- Handle malformed URLs gracefully with validation and error reporting

### 2. Data Extraction & Storage
- Extract the following fields (when available):
  - Profile ID (numeric)
  - Profile Name
  - Public bio/intro
  - Follower count (if visible)
  - Resolved/canonical URL
  - HTTP status
  - Timestamp of fetch
- Store data in structured format (JSON, CSV, SQLite-compatible structure)
- Support incremental updates (don't re-fetch existing profiles)
- Include data deduplication logic

### 3. User Interface Requirements
- **File Upload**: Drag-and-drop or file picker for .txt files
- **URL Preview**: Display first 10 URLs with transformation preview
- **Processing Dashboard**: 
  - Real-time progress bar
  - Current/total count
  - Processing rate (URLs/second)
  - Success/error counts
- **Results Table**: 
  - Sortable columns
  - Filterable (by status, errors)
  - Inline editing for manual corrections
- **Export Options**:
  - Download as JSON
  - Download as CSV
  - Download as SQLite-compatible SQL dump

### 4. Technical Implementation Details

#### Architecture
- Single-file React component using functional components and hooks
- Use Claude API for data extraction (already authenticated, no API key needed)
- Use browser's persistent storage API for data persistence across sessions
- Implement rate limiting (1 request per second to be respectful)

#### Key Features to Implement
```javascript
// URL transformation regex
const transformURL = (url) => {
  const match = url.match(/marketplace\/profile\/(\d+)/);
  return match ? `https://www.facebook.com/${match[1]}` : null;
};

// Data extraction via Claude API
const extractProfileData = async (url) => {
  const response = await fetch("https://api.anthropic.com/v1/messages", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      model: "claude-sonnet-4-20250514",
      max_tokens: 1000,
      messages: [{
        role: "user",
        content: `Fetch this Facebook profile URL: ${url}. Extract: name, bio, follower count if public. Return ONLY JSON: {"name":"","bio":"","followers":""}`
      }]
    })
  });
  return await response.json();
};
```

#### Storage Schema
```javascript
const profileSchema = {
  id: "auto-increment",
  original_url: "string",
  clean_url: "string", 
  profile_id: "string",
  name: "string | null",
  bio: "string | null",
  followers: "string | null",
  http_status: "number | null",
  fetched_at: "ISO timestamp",
  error: "string | null"
};
```

### 5. Error Handling & Edge Cases
- Handle network failures with retry logic (3 attempts)
- Detect rate limiting and pause processing
- Handle non-existent profiles gracefully
- Validate profile IDs are numeric
- Skip duplicate URLs automatically
- Log all errors with context for debugging

### 6. UI/UX Polish
- Use Tailwind CSS for styling (core utility classes only)
- Implement responsive design (mobile-friendly)
- Add loading states for all async operations
- Show toast notifications for success/error states
- Include a "Reset All Data" button with confirmation
- Add keyboard shortcuts (Ctrl+S to export, Ctrl+O to open file)

### 7. Performance Considerations
- Process URLs in batches of 10 with 1-second delays between batches
- Implement virtual scrolling for results table (if >100 rows)
- Debounce search/filter inputs (300ms)
- Use React.memo for expensive components
- Lazy load export functionality

## Output Format Requirements

Create a SINGLE .jsx file that:
1. Implements all features above
2. Has NO external dependencies beyond React and Tailwind
3. Includes inline comments explaining complex logic
4. Has a professional, modern UI design
5. Works immediately when deployed to Claude Artifacts

## Critical Implementation Notes

- **DO NOT** use localStorage (not supported in Claude Artifacts)
- **DO** use `window.storage` API for persistence (shared: false for personal data)
- **DO NOT** use HTML `<form>` tags in React (use div + onClick handlers)
- **DO** implement proper TypeScript-style prop validation in JSDoc comments
- **DO** include example data for testing/demo purposes

## Validation Checklist

Before submitting, verify:
- [ ] File upload works with .txt files
- [ ] URL transformation logic handles all edge cases
- [ ] Claude API calls work without manual API key input
- [ ] Data persists across page reloads
- [ ] Export functions generate valid files
- [ ] UI is responsive on mobile/desktop
- [ ] All error states display helpful messages
- [ ] Processing can be paused/resumed
- [ ] No console errors in browser dev tools

## Success Criteria

The final application should allow a user to:
1. Upload a .txt file with 100+ Facebook Marketplace URLs
2. Transform all URLs to clean format automatically
3. Process them sequentially with visual progress
4. View results in a sortable, filterable table
5. Export to CSV/JSON with one click
6. Resume processing after closing and reopening the page

Build this application with production-quality code, comprehensive error handling, and an intuitive user experience.
