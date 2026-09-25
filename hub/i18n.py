"""Lightweight UI translations (es/en) for the desktop shell.

Keys are stable identifiers; es values MUST reproduce the current UI text
byte-for-byte; en values are natural translations. ``tr()`` supports {arg}
formatting via ``str.format``.
"""

LANGUAGES = {"es": "Español", "en": "English"}
DEFAULT = "es"

STRINGS = {
    "es": {
        # Menu page
        "refresh": "↻ Actualizar",
        "search_placeholder": "Buscar proyectos…",
        "menu_settings": "Configuración",
        # Player page
        "back": "← Volver al menú",
        "variables": "Variables",
        "lists": "Listas",
        "iniciar": "Iniciar",
        "pausar": "Pausar",
        "reanudar": "Reanudar",
        "detener": "Detener",
        "clones": "Clones",
        "clones_active": "Clones activos",
        "fullscreen": "Pantalla completa",
        # Status / errors
        "status_ready": "Listo.",
        "status_load_error": "No se pudieron cargar los proyectos.",
        "error_title": "Error",
        "loading_projects": "Cargando proyectos…",
        "projects_found": "{total} proyectos encontrados.",
        "filter_count": "{visible} de {total} proyectos.",
        "loading": "Cargando…",
        "cached_title": "En caché: {title}",
        "downloading_pid": "Descargando {pid}…",
        "ready_title": "Listo: {title}",
        "download_failed": "No se pudo descargar el proyecto.",
        "player_unavailable": "El reproductor web no está disponible.",
        "player_load_failed": "No se pudo cargar el reproductor web.",
        "unexpected_error": "Error inesperado: {exc}",
        # Variables / lists panel
        "var_title": "Variables — {title}",
        "list_title": "Listas — {title}",
        "col_save": "Guardar",
        "col_variable": "Variable",
        "col_target": "Objetivo",
        "col_value": "Valor",
        "open_project_first": "Primero abrí un proyecto.",
        "panel_info": "La ventana del juego sigue funcionando mientras este panel está abierto. Hacé doble clic en un valor para editarlo.",
        "show_variables_failed": "No se pudieron mostrar las variables: {exc}",
        "edit_list_prompt": "Nuevos elementos separados por coma o JSON para «{name}»:",
        "edit_value_prompt": "Nuevo valor para «{name}»:",
        "edit_value_title": "Editar valor",
        "variable_updated": "Variable «{name}» actualizada.",
        "variable_update_failed": "No se pudo actualizar la variable: {exc}",
        # Settings dialog
        "settings_title": "Configuración",
        "settings_language": "Idioma",
        "close": "Cerrar",
        # Project cards
        "card_meta": "ID: {pid} • @{author}",
        "no_author": "(sin autor)",
        "featured_badge": "★ Destacado",
        "card_cached": "en caché",
        "card_missing": "no descargado",
        "no_thumbnail": "Sin miniatura",
        "project_default_title": "Proyecto {pid}",
        # Project detail dialog
        "play": "▶ Jugar",
        "open_in_scratch": "Abrir en Scratch",
        "favorite_add": "❤ Añadir a favoritos",
        "favorite_remove": "❤ Quitar de favoritos",
        "stats_views": "👁 {n}",
        "stats_loves": "❤ {n}",
        "stats_favorites": "⭐ {n}",
        "stats_remixes": "🔀 {n}",
        "section_description": "Descripción",
        "section_instructions": "Instrucciones",
        "no_description": "Sin descripción.",
        "no_instructions": "Sin instrucciones.",
        "section_comments": "Comentarios",
        "comments_loading": "Cargando comentarios…",
        "no_comments": "Sin comentarios todavía.",
        "comments_unavailable": "No se pudieron cargar los comentarios.",
        "no_cover": "Sin portada",
        "project_detail_title": "Detalles del proyecto",
        # Scratch API
        "scratch_http_error": "La API de Scratch respondió con error HTTP {code} al {action}.",
        "scratch_http_action_list": "listar los proyectos",
        "scratch_http_action_user": "listar los proyectos del usuario",
        "scratch_http_action_project": "obtener el proyecto",
        "scratch_project_error": "No se pudo obtener el proyecto {project_id}: {exc}",
        "scratch_project_invalid": "Respuesta inválida al obtener el proyecto {project_id}.",
        "scratch_http_action_project": "obtener el proyecto",
        "scratch_contact": "No se pudo contactar a la API de Scratch: {exc}",
        "scratch_invalid_response": "La API de Scratch devolvió una respuesta inválida.",
        "scratch_incomplete": "La API de Scratch devolvió datos incompletos.",
        "scratch_project_error": "No se pudo obtener el proyecto {project_id}: {exc}",
        "scratch_project_invalid": "Respuesta inválida al obtener el proyecto {project_id}.",
        "scratch_token_error": "No se pudo obtener el token del proyecto {project_id}: {exc}",
        "scratch_token_invalid": "Respuesta inválida al obtener el token del proyecto {project_id}.",
        "scratch_no_token": "El proyecto {project_id} no tiene token de descarga.",
        "scratch_download_error": "No se pudo descargar el proyecto {project_id}: {exc}",
        "scratch_downloaded_empty": "El proyecto {project_id} se descargó vacío.",
        "scratch_thumb_error": "No se pudo descargar la miniatura del proyecto {project_id}: {exc}",
        "scratch_thumb_save_error": "No se pudo guardar la miniatura del proyecto {project_id}: {exc}",
        "scratch_thumb_save2_error": "No se pudo guardar la miniatura del proyecto {project_id}: {exc}",
        "scratch_thumb_empty": "La miniatura del proyecto {project_id} llegó vacía.",
        "scratch_avatar_error": "No se pudo descargar el avatar del creador {creator_id}: {exc}",
        "scratch_avatar_save_error": "No se pudo descargar el avatar del creador {creator_id}: {exc}",
        "scratch_avatar_save2_error": "No se pudo descargar el avatar del creador {creator_id}: {exc}",
        "scratch_avatar_empty": "El avatar del creador {creator_id} llegó vacío.",
    },
    "en": {
        # Menu page
        "refresh": "↻ Refresh",
        "search_placeholder": "Search projects…",
        "menu_settings": "Settings",
        # Player page
        "back": "← Back to menu",
        "variables": "Variables",
        "lists": "Lists",
        "iniciar": "Play",
        "pausar": "Pause",
        "reanudar": "Resume",
        "detener": "Stop",
        "clones": "Clones",
        "clones_active": "Active clones",
        "fullscreen": "Fullscreen",
        # Status / errors
        "status_ready": "Ready.",
        "status_load_error": "Couldn't load the projects.",
        "error_title": "Error",
        "loading_projects": "Loading projects…",
        "projects_found": "{total} projects found.",
        "filter_count": "{visible} of {total} projects.",
        "loading": "Loading…",
        "cached_title": "Cached: {title}",
        "downloading_pid": "Downloading {pid}…",
        "ready_title": "Ready: {title}",
        "download_failed": "Couldn't download the project.",
        "player_unavailable": "The web player is not available.",
        "player_load_failed": "Couldn't load the web player.",
        "unexpected_error": "Unexpected error: {exc}",
        # Variables / lists panel
        "var_title": "Variables — {title}",
        "list_title": "Lists — {title}",
        "col_save": "Save",
        "col_variable": "Variable",
        "col_target": "Target",
        "col_value": "Value",
        "open_project_first": "Open a project first.",
        "panel_info": "The game window keeps running while this panel is open. Double-click a value to edit it.",
        "show_variables_failed": "Couldn't show the variables: {exc}",
        "edit_list_prompt": "New comma-separated items or JSON for \"{name}\":",
        "edit_value_prompt": "New value for \"{name}\":",
        "edit_value_title": "Edit value",
        "variable_updated": "Variable \"{name}\" updated.",
        "variable_update_failed": "Couldn't update the variable: {exc}",
        # Settings dialog
        "settings_title": "Settings",
        "settings_language": "Language",
        "close": "Close",
        # Project cards
        "card_meta": "ID: {pid} • @{author}",
        "no_author": "(no author)",
        "featured_badge": "★ Featured",
        "card_cached": "cached",
        "card_missing": "not downloaded",
        "no_thumbnail": "No thumbnail",
        "project_default_title": "Project {pid}",
        # Project detail dialog
        "play": "Play",
        "open_in_scratch": "Open in Scratch",
        "favorite_add": "❤ Add to favorites",
        "favorite_remove": "❤ Remove from favorites",
        "stats_views": "👁 {n}",
        "stats_loves": "❤ {n}",
        "stats_favorites": "⭐ {n}",
        "stats_remixes": "🔀 {n}",
        "section_description": "Description",
        "section_instructions": "Instructions",
        "no_description": "No description.",
        "no_instructions": "No instructions.",
        "section_comments": "Comments",
        "comments_loading": "Loading comments…",
        "no_comments": "No comments yet.",
        "comments_unavailable": "Couldn't load the comments.",
        "no_cover": "No cover",
        "project_detail_title": "Project details",
        # Scratch API
        "scratch_http_error": "The Scratch API responded with HTTP error {code} while {action}.",
        "scratch_http_action_list": "listing the projects",
        "scratch_http_action_user": "listing the user's projects",
        "scratch_http_action_project": "fetching the project",
        "scratch_project_error": "Could not fetch project {project_id}: {exc}",
        "scratch_project_invalid": "Invalid response while fetching project {project_id}.",
        "scratch_http_action_project": "fetching the project",
        "scratch_contact": "Couldn't reach the Scratch API: {exc}",
        "scratch_invalid_response": "The Scratch API returned an invalid response.",
        "scratch_incomplete": "The Scratch API returned incomplete data.",
        "scratch_project_error": "Could not fetch project {project_id}: {exc}",
        "scratch_project_invalid": "Invalid response while fetching project {project_id}.",
        "scratch_token_error": "Couldn't get the token for project {project_id}: {exc}",
        "scratch_token_invalid": "Invalid response while getting the token for project {project_id}.",
        "scratch_no_token": "Project {project_id} has no download token.",
        "scratch_download_error": "Couldn't download project {project_id}: {exc}",
        "scratch_downloaded_empty": "Project {project_id} was downloaded empty.",
        "scratch_thumb_error": "Couldn't download the thumbnail for project {project_id}: {exc}",
        "scratch_thumb_save_error": "Couldn't save the thumbnail for project {project_id}: {exc}",
        "scratch_thumb_save2_error": "Couldn't save the thumbnail for project {project_id}: {exc}",
        "scratch_thumb_empty": "The thumbnail for project {project_id} arrived empty.",
        "scratch_avatar_error": "Couldn't download the avatar for creator {creator_id}: {exc}",
        "scratch_avatar_save_error": "Couldn't save the avatar for creator {creator_id}: {exc}",
        "scratch_avatar_save2_error": "Couldn't save the avatar for creator {creator_id}: {exc}",
        "scratch_avatar_empty": "The avatar for creator {creator_id} arrived empty.",
    },
}

_current = DEFAULT


def set_language(lang) -> None:
    """Switch the active language; unknown codes fall back to DEFAULT."""
    global _current
    _current = lang if lang in LANGUAGES else DEFAULT


def current() -> str:
    """Return the active language code (default: "es")."""
    return _current


def tr(key, **kwargs) -> str:
    """Translate ``key`` for the current language (fallback en -> es -> key).

    Optional ``kwargs`` are applied with ``str.format`` when the catalog value
    declares ``{arg}`` placeholders.
    """
    for lang in (_current, "en", "es"):
        value = STRINGS.get(lang, {}).get(key)
        if value is not None:
            return value.format(**kwargs) if kwargs else value
    return key