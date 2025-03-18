import asyncio
import hashlib
import json
import logging
import os
import shutil
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Optional

from fastapi import FastAPI
from mcp.server.fastmcp import FastMCP

# Configure logging
logger = logging.getLogger('pinthepiece.server')
logger.setLevel(logging.DEBUG)

# Create file handler if not already configured
if not logger.handlers:
    # Create file handler
    log_dir = os.path.expanduser('~/.pinthepiece/logs')
    os.makedirs(log_dir, exist_ok=True)
    fh = logging.FileHandler(os.path.join(log_dir, 'pinthepiece.log'))
    fh.setLevel(logging.DEBUG)

    # Create console handler
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)

    # Create formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    fh.setFormatter(formatter)
    ch.setFormatter(formatter)

    # Add handlers to logger
    logger.addHandler(fh)
    logger.addHandler(ch)

@dataclass
class Note:
    VERSION = "1.0.0"  # Current note format version

    name: str
    content: str
    created: datetime
    modified: datetime
    tags: list[str]
    description: Optional[str] = None
    metadata: dict = field(default_factory=lambda: {
        "format_version": Note.VERSION,
        "last_backup": None,
        "checksum": None
    })

    def to_dict(self) -> dict:
        data = {
            'name': self.name,
            'content': self.content,
            'tags': self.tags,
            'description': self.description,
            'created': self.created.isoformat(),
            'version': self.VERSION,
            'metadata': self.metadata,
        }
        data['modified'] = self.modified.isoformat()
        # Update checksum before saving
        content_str = (
            f"{self.content}{self.created.isoformat()}"
            f"{self.modified.isoformat()}"
        )
        self.metadata['checksum'] = hashlib.sha256(content_str.encode()).hexdigest()
        return data

    @classmethod
    def from_dict(cls, data: dict) -> 'Note':
        version = data.get('version', 0)
        if version > cls.VERSION:
            raise ValueError(
                f"Note version {version} is newer than supported version {cls.VERSION}"
            )

        # Create note instance
        note = cls(
            name=data['name'],
            content=data['content'],
            tags=data.get('tags', []),
            description=data.get('description'),
            created=datetime.fromisoformat(data['created']),
            modified=datetime.fromisoformat(data['modified']),
            metadata=data.get('metadata', {}),
        )

        # Validate checksum if available
        if metadata.get('checksum'):
            content_str = (
                f"{note.content}{note.created.isoformat()}"
                f"{note.modified.isoformat()}"
            )
            current_checksum = hashlib.sha256(content_str.encode()).hexdigest()
            if current_checksum != metadata['checksum']:
                raise ValueError("Note content checksum validation failed")

        return note

class ResourceManager:
    def __init__(self, storage_dir: str = None):
        self.notes: dict[str, Note] = {}
        self._lock = asyncio.Lock()
        self._subscribers: list[asyncio.Queue] = []

        # Set up storage directory structure
        self.storage_dir = storage_dir or os.path.expanduser('~/.pinthepiece')
        self.notes_dir = os.path.join(self.storage_dir, 'notes')
        self.data_dir = os.path.join(self.notes_dir, 'data')
        self.backup_dir = os.path.join(self.notes_dir, 'backups')
        self.index_file = os.path.join(self.notes_dir, 'index.json')

        # Create directory structure
        for directory in [self.storage_dir, self.notes_dir, self.data_dir, self.backup_dir]:
            os.makedirs(directory, exist_ok=True)

        logger.info(f"Initialized ResourceManager with storage directory: {self.storage_dir}")

        # Initialize index if it doesn't exist
        if not os.path.exists(self.index_file):
            self._save_index({})

        # Load existing notes
        self._load_notes()

    def _get_note_path(self, name: str, created: datetime = None) -> str:
        """Get the hierarchical file path for a note."""
        if created is None:
            # If no creation date provided, try to get it from index
            index = self._load_index()
            if name in index:
                created = datetime.fromisoformat(index[name]['created'])
            else:
                created = datetime.now()

        # Create hierarchical path: year/month
        year_dir = os.path.join(self.data_dir, str(created.year))
        month_dir = os.path.join(year_dir, f"{created.month:02d}")
        os.makedirs(month_dir, exist_ok=True)

        safe_name = "".join(c if c.isalnum() or c in ('-', '_') else '_' for c in name)
        return os.path.join(month_dir, f"{safe_name}.json")

    def _load_index(self) -> dict:
        """Load the note index file."""
        try:
            if os.path.exists(self.index_file):
                with open(self.index_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            logger.error(f"Error loading index: {e}", exc_info=True)
        return {}

    def _save_index(self, index: dict) -> None:
        """Save the note index file atomically."""
        temp_path = f"{self.index_file}.tmp"
        try:
            with open(temp_path, 'w', encoding='utf-8') as f:
                json.dump(index, f, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp_path, self.index_file)
        except Exception as e:
            logger.error(f"Error saving index: {e}", exc_info=True)
            if os.path.exists(temp_path):
                os.unlink(temp_path)

    def _create_backup(self, note_path: str) -> str:
        """Create a backup of a note file."""
        if not os.path.exists(note_path):
            return None

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_name = f"{os.path.basename(note_path)}.{timestamp}.bak"
        backup_path = os.path.join(self.backup_dir, backup_name)

        try:
            shutil.copy2(note_path, backup_path)
            return backup_path
        except Exception as e:
            logger.error(f"Error creating backup: {e}", exc_info=True)
            return None

    async def _save_note(self, name: str, note: Note) -> None:
        """Save a note to disk with atomic operations and backup."""
        file_path = self._get_note_path(name, note.created)
        logger.debug(f"Saving note {name} to: {file_path}")

        # Create backup of existing file
        if os.path.exists(file_path):
            backup_path = self._create_backup(file_path)
            if backup_path:
                note.metadata['last_backup'] = datetime.now().isoformat()
                logger.debug(f"Created backup at: {backup_path}")

        # Update index
        index = self._load_index()
        index[name] = {
            'path': file_path,
            'created': note.created.isoformat(),
            'modified': note.modified.isoformat(),
            'version': note.VERSION
        }

        # Save note file atomically
        temp_path = f"{file_path}.tmp"
        try:
            # Ensure directory exists
            os.makedirs(os.path.dirname(file_path), exist_ok=True)

            # Write to temporary file
            with open(temp_path, 'w', encoding='utf-8') as f:
                json.dump(note.to_dict(), f, indent=2, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())

            # Atomic rename
            os.replace(temp_path, file_path)

            # Update index after successful save
            self._save_index(index)

            logger.info(f"Successfully saved note: {name}")

        except Exception as e:
            logger.error(f"Error saving note {name}: {e}", exc_info=True)
            if os.path.exists(temp_path):
                try:
                    os.unlink(temp_path)
                except Exception:
                    pass
            raise

    def _load_notes(self) -> None:
        """Load all notes from disk using the index."""
        if not os.path.exists(self.notes_dir):
            logger.warning(f"Notes directory does not exist: {self.notes_dir}")
            return

        logger.info(f"Loading notes from: {self.notes_dir}")
        loaded_count = 0
        error_count = 0

        # Load from index
        index = self._load_index()
        for name, info in index.items():
            file_path = info['path']
            if not os.path.exists(file_path):
                logger.warning(f"Note file missing: {file_path}")
                continue

            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.notes[name] = Note.from_dict(data)
                    loaded_count += 1
                    logger.debug(f"Loaded note: {name} from {file_path}")
            except json.JSONDecodeError as e:
                error_count += 1
                logger.error(f"JSON decode error loading note {name}: {e}")
            except Exception as e:
                error_count += 1
                logger.error(f"Error loading note {name}: {e}", exc_info=True)

        logger.info(f"Loaded {loaded_count} notes successfully, {error_count} errors")

    async def subscribe_to_changes(self) -> asyncio.Queue:
        """Subscribe to resource changes."""
        queue = asyncio.Queue()
        self._subscribers.append(queue)
        return queue

    async def unsubscribe(self, queue: asyncio.Queue) -> None:
        """Unsubscribe from resource changes."""
        if queue in self._subscribers:
            self._subscribers.remove(queue)

    async def _notify_changes(self) -> None:
        """Notify all subscribers of resource changes."""
        for subscriber in self._subscribers:
            await subscriber.put("resource_changed")

    async def add_note(
        self, 
        name: str, 
        content: str, 
        tags: list[str] = None, 
        description: str = None
    ) -> Note:
        """Add a new note."""
        logger.info(f"Adding new note: {name}")

        async with self._lock:
            if name in self.notes:
                raise ValueError(f"Note already exists: {name}")

            # Create note object
            note = Note(
                name=name,
                content=content,
                tags=tags or [],
                description=description
            )
            logger.debug(
                f"Created note object for {name} with {len(content)} characters"
            )

            # Create note path based on creation date
            try:
                self._save_note(name, note)
                index = self._load_index()
                index['notes'][name] = {
                    'path': self._get_note_path(name),
                    'created': note.created.isoformat(),
                }
                self._save_index(index)
            except Exception as e:
                logger.error(f"Failed to save note {name}: {e}", exc_info=True)
                raise ValueError(f"Failed to save note: {e}") from e

            # If save successful, update memory
            self.notes[name] = note
            await self._notify_changes()
            return note

    async def get_note(self, name: str) -> Note:
        async with self._lock:
            if name not in self.notes:
                raise ValueError(f"Note not found: {name}")
            return self.notes[name]

    async def update_note(
        self, 
        name: str, 
        content: str = None, 
        tags: list[str] = None, 
        description: str = None
    ) -> Note:
        """Update an existing note."""
        logger.info(f"Updating note: {name}")

        async with self._lock:
            if name not in self.notes:
                raise ValueError(f"Note not found: {name}")

            note = self.notes[name]

            # Update fields if provided
            if content is not None:
                note.content = content
            if tags is not None:
                note.tags = tags
            if description is not None:
                note.description = description

            note.modified = datetime.now()

            logger.debug(
                f"Modified note {name} with new content length: {len(note.content)}"
            )

            # Save to disk first
            try:
                await asyncio.to_thread(self._save_note, name, note)
            except Exception as e:
                logger.error(
                    f"Failed to save updated note {name}: {e}", 
                    exc_info=True
                )
                raise ValueError(f"Failed to save note: {e}") from e

            await self._notify_changes()
            return note

    async def delete_note(self, name: str) -> None:
        """Delete a note."""
        logger.info(f"Deleting note: {name}")
        async with self._lock:
            if name not in self.notes:
                logger.warning(f"Note not found for deletion: {name}")
                raise ValueError(f"Note not found: {name}")

            # Remove from memory
            del self.notes[name]

            # Remove from disk
            file_path = self._get_note_path(name)
            try:
                if os.path.exists(file_path):
                    os.unlink(file_path)
                    logger.debug(f"Deleted note file: {file_path}")
            except Exception as e:
                logger.error(f"Error deleting note file {name}: {e}", exc_info=True)

            await self._notify_changes()
            logger.info(f"Successfully deleted note: {name}")

    async def list_notes(self) -> list[str]:
        async with self._lock:
            return list(self.notes.keys())

    async def get_note_content(self, name: str) -> str:
        note = await self.get_note(name)
        return note.content

    async def search_notes(
        self, 
        query: str, 
        search_in: list[str] = None, 
        match_all_tags: bool = False
    ) -> dict[str, Note]:
        """Search through notes based on content, tags, and description.
        
        Args:
            query: The search query string
            search_in: List of fields to search in ('content', 'tags', 'description'). 
                      If None, search in all fields.
            match_all_tags: If True, when searching tags, all query tags must match. 
                          If False, any tag match is sufficient.
        
        Returns:
            Dictionary of matching note names and their Note objects
        """
        query = query.lower()
        search_fields = search_in or ['content', 'tags', 'description']
        results = {}

        async with self._lock:
            # If searching in tags and query looks like tags, split them
            query_tags = (
                [t.strip() for t in query.split(',')]
                if 'tags' in search_fields and ',' in query
                else [query]
            )

            for name, note in self.notes.items():
                matched = False

                if 'content' in search_fields and query in note.content.lower():
                    matched = True

                if ('description' in search_fields and note.description 
                    and query in note.description.lower()):
                    matched = True

                if 'tags' in search_fields and note.tags:
                    if match_all_tags:
                        # All query tags must be present in note tags
                        if all(
                            any(qt in t.lower() for t in note.tags)
                            for qt in query_tags
                        ):
                            matched = True
                    else:
                        # Any query tag match is sufficient
                        if any(
                            any(qt in t.lower() for t in note.tags)
                            for qt in query_tags
                        ):
                            matched = True

                if matched:
                    results[name] = note

        return results

# Initialize the resource manager as a singleton
_resource_manager = None

def get_resource_manager() -> ResourceManager:
    """Get or create the singleton ResourceManager instance."""
    global _resource_manager
    if _resource_manager is None:
        logger.info("Creating new ResourceManager instance")
        _resource_manager = ResourceManager()
    return _resource_manager

# Use the singleton resource manager
resource_manager = get_resource_manager()

# Create FastAPI app instance for HTTP server mode
app = FastAPI(title="PinThePiece")

# Initialize FastMCP server
mcp_server = FastMCP("pinthepiece")

@mcp_server.resource("note://{name}")
async def note_resource(name: str) -> str:
    """Provide note content as a resource."""
    try:
        note = await resource_manager.get_note(name)
        return note.content
    except ValueError:
        raise ValueError(f"Note not found: {name}")

@mcp_server.tool()
async def get_note(name: str) -> str:
    """Get a note's content."""
    try:
        note = await resource_manager.get_note(name)
        return note.content
    except ValueError:
        raise ValueError(f"Note not found: {name}") from None

@mcp_server.tool()
async def add_note(
    name: str, 
    content: str, 
    tags: list[str] = None, 
    description: str = None
) -> str:
    """Add a new note to the server."""
    try:
        note = await resource_manager.add_note(name, content, tags, description)
        return (
            f"Successfully added note '{name}'\n"
            f"Tags: {note.tags}\n"
            f"Description: {note.description or 'No description'}"
        )
    except ValueError as e:
        raise ValueError(str(e)) from e

@mcp_server.tool()
async def update_note(
    name: str, 
    content: str = None, 
    tags: list[str] = None, 
    description: str = None
) -> str:
    """Update an existing note."""
    try:
        await resource_manager.update_note(name, content, tags, description)
        return f"Successfully updated note '{name}'"
    except ValueError as e:
        raise ValueError(str(e)) from e

@mcp_server.tool()
async def delete_note(name: str) -> str:
    """Delete a note."""
    try:
        await resource_manager.delete_note(name)
        return f"Successfully deleted note '{name}'"
    except ValueError as e:
        raise ValueError(str(e)) from e

@mcp_server.tool()
async def list_notes() -> str:
    """List all available notes."""
    notes = await resource_manager.list_notes()
    if not notes:
        return "No notes found"

    result = []
    for name in notes:
        note = await resource_manager.get_note(name)
        result.append(
            f"Note: {name}\n"
            f"Tags: {note.tags}\n"
            f"Created: {note.created.isoformat()}\n"
            f"Description: {note.description or 'No description'}\n"
            "---"
        )
    return "\n\n".join(result)

@mcp_server.tool()
async def search_notes(
    query: str, 
    search_in: list[str] = None, 
    match_all_tags: bool = False
) -> str:
    """Search through notes."""
    results = await resource_manager.search_notes(query, search_in, match_all_tags)
    if not results:
        return "No matching notes found."

    result = []
    for name, note in results.items():
        result.append(
            f"Note: {name}\n"
            f"Content: {note.content[:100]}...\n"
            f"Tags: {note.tags}\n"
            f"Created: {note.created.isoformat()}\n"
            f"Description: {note.description or 'No description'}\n"
            "---"
        )
    return f"Found {len(results)} matching note(s):\n\n" + "\n\n".join(result)

@mcp_server.prompt()
async def summarize_notes(style: str = "brief") -> str:
    """Create a summary of all notes."""
    notes = await resource_manager.list_notes()
    if not notes:
        return "No notes to summarize."

    result = []
    for name in notes:
        note = await resource_manager.get_note(name)
        if style == "brief":
            result.append(f"- {name}: {note.content[:50]}...")
        else:
            result.append(
                f"Note: {name}\n"
                f"Content: {note.content}\n"
                f"Tags: {note.tags}\n"
                f"Created: {note.created.isoformat()}\n"
                f"Description: {note.description or 'No description'}"
            )

    style_text = "Brief summary" if style == "brief" else "Detailed summary"
    return f"{style_text} of {len(notes)} notes:\n\n" + "\n\n".join(result)

def main():
    """Run the server."""
    mcp_server.run()

if __name__ == "__main__":
    main()
