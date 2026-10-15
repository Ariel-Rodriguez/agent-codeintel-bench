"""Leaf constants shared by the widget package.

Kept in a leaf module so decision code can import bounds without importing the
package ``__init__`` and creating an import cycle.
"""

SEMANTIC_TEXT_LIMIT = 8000
TYPING_LIMIT_CHARS = 4096
