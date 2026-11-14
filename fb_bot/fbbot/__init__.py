"""fbbot - automação de Páginas do Facebook e Reels via Graph API oficial."""
from .graph import GraphClient, GraphError, Page

__all__ = ["GraphClient", "GraphError", "Page"]
