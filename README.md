# Kentik AI Advisor Slackbot

A Slack bot application that enables seamless communication between Slack users and Kentik's AI Advisor REST API. Users can ask questions about their network by mentioning the bot (`@kentik`) in Slack channels or sending direct messages.

## Features

- **Natural Interaction**: Use `@kentik` mentions in channels or send direct messages
- **Thread-based Conversations**: Responses appear in threads, maintaining conversation context
- **Conversation Continuity**: Follow-up questions in threads continue the same AI Advisor session
- **Context-Aware**: When starting a conversation in an existing thread, includes context from previous messages
- **Asynchronous Processing**: Handles AI Advisor's asynchronous response pattern with polling
- **Persistent Storage**: SQLite database maintains mapping between Slack threads and AI Advisor sessions

## Prerequisites

- Python 3.10 or higher
- [UV package manager](https://github.com/astral-sh/uv)
- Slack workspace with admin access
- Kentik account with API credentials
- Slack app configured with appropriate permissions

## Installation

### Using UV (Recommended)

1. Clone the repository:
```bash
git clone <repository-url>
cd kentik-ai-advisor-slackbot
```

2. Install UV if you haven't already:
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

3. Create virtual environment and install dependencies:
```bash
uv venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
uv pip install -e .
```

### Using pip

```bash
pip install -e .
```

## Slack App Configuration

### 1. Create Slack App

1. Go to [Slack API](https://api.slack.com/apps) and click "Create New App"
2. Choose "From scratch"
3. Enter app name (e.g., "Kentik AI Advisor") and select your workspace
4. Click "Create App"

### 2. Enable Socket Mode

1. Navigate to "Settings → Socket Mode"
2. Enable Socket Mode
3. Generate an app-level token with `connections:write` scope
4. Save the token as `SLACK_APP_TOKEN` in your `.env` file

### 3. Configure Bot User

1. Go to "Features → App Home"
2. Configure:
   - Display Name: "Kentik AI Advisor"
   - Default Username: "kentik"
   - Enable "Always Show My Bot as Online"
3. Under "Show Tabs":
   - Disable "Home Tab"
   - Enable "Messages Tab"
   - Check "Allow users to send Slash commands and messages from the messages tab"

### 4. Add Bot Scopes

Navigate to "Features → OAuth & Permissions" and add these Bot Token Scopes:

- `app_mentions:read` - Listen for @mentions
- `channels:history` - Read channel messages
- `channels:read` - View basic channel info
- `chat:write` - Send messages
- `im:history` - Read DM messages
- `im:read` - View DM info
- `im:write` - Send DMs

### 5. Subscribe to Events

Go to "Features → Event Subscriptions" and enable events. Subscribe to these bot events:

- `app_mention` - When bot is mentioned
- `message.im` - Direct messages to bot

### 6. Install App to Workspace

1. Go to "Settings → Install App"
2. Click "Install to Workspace"
3. Authorize the app
4. Copy the "Bot User OAuth Token" as `SLACK_BOT_TOKEN` for your `.env` file

### Example App Manifest

You can also use this manifest to configure your app:

```yaml
display_information:
  name: Kentik AI Advisor
  description: AI-powered network analysis assistant
  background_color: "#333436"
features:
  app_home:
    home_tab_enabled: false
    messages_tab_enabled: true
    messages_tab_read_only_enabled: false
  bot_user:
    display_name: Kentik AI Advisor
    always_online: true
oauth_config:
  scopes:
    bot:
      - app_mentions:read
      - channels:history
      - channels:read
      - chat:write
      - im:history
      - im:read
      - im:write
settings:
  event_subscriptions:
    bot_events:
      - app_mention
      - message.im
  org_deploy_enabled: false
  socket_mode_enabled: true
  token_rotation_enabled: false
```

## Configuration

### Environment Variables

1. Copy the example environment file:
```bash
cp .env.example .env
```

2. Edit `.env` with your credentials:

```bash
# Slack Configuration
SLACK_BOT_TOKEN=xoxb-your-bot-token
SLACK_APP_TOKEN=xapp-your-app-token

# Kentik API Configuration
KENTIK_API_URL=https://grpc.api.kentik.com  # or https://grpc.api.kentik.eu
KENTIK_API_EMAIL=your-email@company.com
KENTIK_API_TOKEN=your-api-token

# Optional Configuration
THREAD_CONTEXT_MESSAGES=5
POLLING_INTERVAL_SECONDS=2
POLLING_TIMEOUT_SECONDS=120
CONVERSATIONS_DB_PATH=conversations.db
```

### Getting Kentik API Credentials

1. Log into [Kentik Portal](https://portal.kentik.com)
2. Click your profile (top-right)
3. Go to "Authentication" tab
4. Copy your API Token

### Configuration Options

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `SLACK_BOT_TOKEN` | Yes | - | Slack Bot User OAuth Token |
| `SLACK_APP_TOKEN` | Yes | - | Slack App-Level Token |
| `KENTIK_API_URL` | Yes | - | Kentik API URL (US/EU cluster) |
| `KENTIK_API_EMAIL` | Yes | - | Kentik account email |
| `KENTIK_API_TOKEN` | Yes | - | Kentik API token |
| `THREAD_CONTEXT_MESSAGES` | No | 5 | Number of previous messages to include as context |
| `POLLING_INTERVAL_SECONDS` | No | 2 | Polling interval in seconds (min: 2) |
| `POLLING_TIMEOUT_SECONDS` | No | 120 | Max wait time for AI response in seconds |
| `CONVERSATIONS_DB_PATH` | No | conversations.db | Path to SQLite database file |

## Usage

### Running Locally

```bash
uv run kentik-ai-advisor-slackbot
```

### Running with Docker

1. Build the Docker image:
```bash
docker build -t kentik-ai-advisor-slackbot .
```

2. Run the container:
```bash
docker run -d --restart unless-stopped \
  --name kentik-ai-advisor-slackbot \
  -e SLACK_BOT_TOKEN='xoxb-your-token' \
  -e SLACK_APP_TOKEN='xapp-your-token' \
  -e KENTIK_API_URL='https://grpc.api.kentik.com' \
  -e KENTIK_API_EMAIL='your-email@company.com' \
  -e KENTIK_API_TOKEN='your-api-token' \
  kentik-ai-advisor-slackbot:latest
```

Or use a `.env` file:
```bash
docker run -d --restart unless-stopped \
  --name kentik-ai-advisor-slackbot \
  --env-file .env \
  -v $(pwd)/conversations.db:/app/conversations.db \
  kentik-ai-advisor-slackbot:latest
```

## How It Works

### Conversation Flow

#### 1. New Conversation in Channel
- User mentions bot in channel: `@kentik show me top talkers`
- Bot creates new AI Advisor session
- Response posted in thread
- Thread/session mapping saved to database

#### 2. Follow-up in Thread
- User replies in thread: `@kentik what about the last 24 hours?`
- Bot retrieves existing session ID from database
- Updates AI Advisor session with follow-up question
- Maintains conversation context

#### 3. New Conversation in Existing Thread
- User mentions bot in thread not started by bot
- Bot creates new session with context:
  - First message in thread
  - Previous 5 messages (configurable)
- Response posted in same thread

#### 4. Direct Messages
- User sends DM to bot
- Treated as new conversation
- No threading (DMs don't support threads)

### Thread and Session Management

The bot maintains a SQLite database (`conversations.db`) that maps:
- Slack thread timestamp → AI Advisor session UUID
- Channel ID for reference
- Created/updated timestamps

This allows the bot to:
- Continue conversations across multiple questions
- Maintain conversation history
- Support multiple concurrent conversations

### AI Advisor API Integration

The bot handles AI Advisor's asynchronous pattern:
1. Submit question (POST/PUT)
2. Receive session ID and PENDING status
3. Poll every 2 seconds (GET)
4. Wait for COMPLETED or FAILED status
5. Process and format response
6. Post to Slack

## Development

### Project Structure

```
kentik-ai-advisor-slackbot/
├── kentik_ai_advisor_slackbot/
│   ├── __init__.py
│   ├── app.py                    # Main Slack bot logic
│   ├── ai_advisor_client.py       # AI Advisor API client
│   └── conversation_store.py      # SQLite database layer
├── .env.example
├── .gitignore
├── Dockerfile
├── pyproject.toml
└── README.md
```

## Troubleshooting

### Bot doesn't respond to mentions

1. Check bot is running: `docker logs kentik-ai-advisor-slackbot`
2. Verify Socket Mode is enabled in Slack app settings
3. Ensure `SLACK_APP_TOKEN` and `SLACK_BOT_TOKEN` are correct
4. Check bot has `app_mentions:read` scope

### Conversations not continuing

1. Check database file exists and is writable
2. Verify thread timestamps are consistent
3. Check logs for database errors

### AI Advisor timeouts

1. Increase `POLLING_TIMEOUT_SECONDS` (default: 120s)
2. Check Kentik API credentials are valid
3. Verify network connectivity to Kentik API

### Rate limiting

AI Advisor has rate limits:
- 4 requests/minute for create/update
- 60 requests/minute for get

The bot respects these limits with 2-second polling intervals.

## License

MIT

## Support

For issues and questions:
- GitHub Issues: this repository
- Kentik Support: https://support.kentik.com
