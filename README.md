# PinThePiece MCP server

A robust Model Context Protocol (MCP) server that provides a sophisticated note management system. This server implements a feature-rich note storage solution with emphasis on data integrity, organization, and accessibility. Key features include hierarchical storage, atomic operations, versioning support, automatic backups, and comprehensive search capabilities.

## Features

### Note Storage System

The server implements a sophisticated note storage system with:
- Hierarchical storage structure for better organization and scalability
- Atomic file operations for data integrity
- Versioning and metadata support
- Automatic backups
- Concurrent access handling
- Comprehensive logging

#### Storage Structure
```
~/.pinthepiece/
├── notes/
│   ├── data/
│   │   └── YEAR/
│   │       └── MONTH/
│   │           └── note-name.json
│   ├── backups/
│   │   └── note-name.json.TIMESTAMP.bak
│   └── index.json
└── logs/
    └── notes.log
```

#### Note Format
Each note is stored as a JSON file with:
- Content: The main text of the note
- Created/Modified timestamps
- Tags for organization
- Description (optional)
- Metadata including:
  - Format version
  - Last backup timestamp
  - Content checksum

### Resources

The server implements a note storage system with:
- Custom note:// URI scheme for accessing individual notes
- Each note resource has:
  - Name: Unique identifier
  - Content: Main text content
  - Description: Optional description
  - Tags: List of categorization tags
  - Metadata: Version and integrity information
  - MIME type: text/plain

### Data Safety Features

- **Atomic Operations**: All file writes use atomic operations to prevent corruption
- **Backup System**: Automatic backups before modifications
- **Version Control**: File format versioning for future compatibility
- **Data Validation**: Checksum verification and integrity checks
- **Concurrent Access**: File locking for thread safety
- **Error Recovery**: Transaction-like operations with rollback capability

### Prompts

The server provides a single prompt:
- summarize-notes: Creates summaries of all stored notes
  - Optional "style" argument to control detail level (brief/detailed)
  - Generates prompt combining all current notes with style preference

### Tools

The server implements one tool:
- add-note: Adds a new note to the server
  - Takes "name" and "content" as required string arguments
  - Optional "tags" and "description" arguments
  - Updates server state and notifies clients of resource changes
  - Performs atomic file operations with backup creation

## Configuration

### Storage Location
By default, the server stores notes in:
- `~/.pinthepiece/notes/` - Main storage directory
- `~/.pinthepiece/logs/` - Log files

### Logging
- Detailed logging of all operations
- Log rotation for space management
- Both file and console logging available
- Configurable log levels

## Quickstart

### Install

#### Claude Desktop

On MacOS: `~/Library/Application\ Support/Claude/claude_desktop_config.json`
On Windows: `%APPDATA%/Claude/claude_desktop_config.json`

<details>
  <summary>Development/Unpublished Servers Configuration</summary>
  ```
  "mcpServers": {
    "pinthepiece": {
      "command": "uv",
      "args": [
        "--directory",
        "/Users/pmoreira/create-python-server/pinthepiece",
        "run",
        "pinthepiece"
      ]
    }
  }
  ```
</details>

<details>
  <summary>Published Servers Configuration</summary>
  ```
  "mcpServers": {
    "pinthepiece": {
      "command": "uvx",
      "args": [
        "pinthepiece"
      ]
    }
  }
  ```
</details>

## Development

### Building and Publishing

To prepare the package for distribution:

1. Sync dependencies and update lockfile:
```bash
uv sync
```

2. Build package distributions:
```bash
uv build
```

This will create source and wheel distributions in the `dist/` directory.

3. Publish to PyPI:
```bash
uv publish
```

Note: You'll need to set PyPI credentials via environment variables or command flags:
- Token: `--token` or `UV_PUBLISH_TOKEN`
- Or username/password: `--username`/`UV_PUBLISH_USERNAME` and `--password`/`UV_PUBLISH_PASSWORD`

### Debugging

Since MCP servers run over stdio, debugging can be challenging. For the best debugging
experience, we strongly recommend using the [MCP Inspector](https://github.com/modelcontextprotocol/inspector).

You can launch the MCP Inspector via [`npm`](https://docs.npmjs.com/downloading-and-installing-node-js-and-npm) with this command:

```bash
npx @modelcontextprotocol/inspector uv --directory /Users/pmoreira/create-python-server/pinthepiece run pinthepiece
```

Upon launching, the Inspector will display a URL that you can access in your browser to begin debugging.

### Error Handling

The server implements comprehensive error handling:
- Detailed error logging with stack traces
- Automatic cleanup of temporary files
- Recovery from interrupted operations
- Backup restoration capability
- Data validation on load/save