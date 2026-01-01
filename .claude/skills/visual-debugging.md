# Visual Debugging Skill

Use this skill for debugging frontend issues by visually inspecting the running application through Chrome browser automation.

## When to Use

- Debugging UI rendering issues
- Verifying component behavior
- Checking responsive layouts
- Inspecting network requests and console errors
- Validating user flows
- Capturing screenshots/GIFs of issues

## Prerequisites

Ensure the application is running locally:

```bash
# Development mode (with Docker)
docker compose -f docker/docker-compose.debug.yaml up

# Or test mode
docker compose -f docker/docker-compose.test.yaml up
```

The app will be available at:
- Frontend: https://localhost (via nginx)
- Backend API: https://localhost/api/

## Available Chrome MCP Tools

### Page Navigation & Context
- `mcp__claude-in-chrome__tabs_context_mcp` - Get current browser tabs (call first!)
- `mcp__claude-in-chrome__tabs_create_mcp` - Create new tab
- `mcp__claude-in-chrome__navigate` - Navigate to URL

### Page Inspection
- `mcp__claude-in-chrome__read_page` - Get accessibility tree of elements
- `mcp__claude-in-chrome__find` - Find elements by natural language
- `mcp__claude-in-chrome__get_page_text` - Extract page text content

### Interactions
- `mcp__claude-in-chrome__computer` - Mouse/keyboard actions (click, type, screenshot)
- `mcp__claude-in-chrome__form_input` - Set form values
- `mcp__claude-in-chrome__javascript_tool` - Execute JavaScript in page context

### Debugging
- `mcp__claude-in-chrome__read_console_messages` - Read console logs/errors
- `mcp__claude-in-chrome__read_network_requests` - Monitor network activity

### Recording
- `mcp__claude-in-chrome__gif_creator` - Record browser interactions as GIF

## Debugging Workflow

### 1. Setup Browser Context
```
1. Call tabs_context_mcp to get available tabs
2. Create new tab with tabs_create_mcp if needed
3. Navigate to the page under investigation
```

### 2. Take Initial Screenshot
```
Use computer tool with action: "screenshot" to capture current state
```

### 3. Inspect the Page
```
- Use read_page to get element tree
- Use find to locate specific elements by description
- Use read_console_messages with pattern filter for errors
- Use read_network_requests to check API calls
```

### 4. Interact and Debug
```
- Use computer tool for clicks and keyboard input
- Use form_input for filling forms
- Use javascript_tool for custom debugging scripts
```

### 5. Record Issues
```
1. Start recording: gif_creator action: "start_recording"
2. Take screenshot immediately after starting
3. Reproduce the issue step by step
4. Take screenshot before stopping
5. Stop recording: gif_creator action: "stop_recording"
6. Export: gif_creator action: "export" with download: true
```

## Example: Debug Login Flow

```
1. tabs_context_mcp (get context)
2. tabs_create_mcp (new tab)
3. navigate to "https://localhost/login"
4. computer action: "screenshot" (initial state)
5. find query: "login button" (locate element)
6. read_console_messages pattern: "error|Error" (check for errors)
7. read_network_requests urlPattern: "/api/auth" (monitor auth calls)
```

## Console Log Patterns

Useful patterns for read_console_messages:
- `"error|Error"` - All errors
- `"warning|Warning"` - All warnings
- `"[MyApp]"` - App-specific logs (if using getLogger)
- `"failed|Failed"` - Failure messages

## Network Request Patterns

Useful patterns for read_network_requests:
- `"/api/"` - All API calls
- `"/api/auth"` - Authentication calls
- `"/api/users"` - User-related calls
- `"/api/tournaments"` - Tournament-related calls

## Tips

- Always call `tabs_context_mcp` first to get valid tab IDs
- Use descriptive `find` queries: "submit button", "username input", "error message"
- Filter console/network to avoid overwhelming output
- Take screenshots before and after actions for comparison
- Use GIF recording for complex multi-step issues
