"use strict";

/* Basic Engine Hub — shared web translations (es, fr, pt, en).
 *
 * Pure helpers plus one table, so the `node --test` suite can exercise every
 * rule and the three web surfaces speak the same language: the menu
 * (web/app.js), the shell (index.html and web/index.html) and the player page
 * (web/player.html, which serves both the browser and the desktop shell).
 *
 * Which language is used, in order:
 *   1. ?lang=<code> in the URL — the desktop shell's contract; hub/player.py
 *      loads the player page as "?lang=" + i18n.current().
 *   2. the stored choice (localStorage, basic-engine-hub:idioma:v1).
 *   3. DEFAULT ("en").
 * An unknown code anywhere in that chain falls back to DEFAULT, and a missing
 * key renders its own name — the same contract web/player.html's uiText() has
 * always had, so a gap shows up visibly instead of rendering empty.
 *
 * The `es` values are the verbatim baseline of the copy this site shipped with,
 * except where a string lived in English inside a Spanish UI (the player page's
 * own leftovers): those keep their English in `en` and gain real translations.
 */

/* This file is a classic script, so everything it declares at the top level
 * lands in the page's shared scope next to the host page's own names (the menu
 * and the player page each declare a `tr` of their own). A collision there is a
 * SyntaxError that kills the second script whole, so the core publishes exactly
 * one global -- `I18n` -- and keeps every helper private to this closure. */
(() => {
  const STORAGE_KEY = "basic-engine-hub:idioma:v1";
  const DEFAULT = "en";

  /* The selector offers exactly these four, in this order. Each flag is an inline
   * SVG: flag emoji do not render as flags on Windows Chrome (they show "ES").
   * `title` is the language's own wordmark under Assets/Lengs/Titles, drawn in
   * that language; the two surfaces show it as the option's visible name. */
  const LANGUAGES = [
    {
      code: "es",
      name: "Español",
      title: "español.png",
      flag: '<svg viewBox="0 0 24 16" aria-hidden="true" focusable="false"><rect width="24" height="16" fill="#AA151B"/><rect y="4" width="24" height="8" fill="#F1BF00"/></svg>',
    },
    {
      code: "fr",
      name: "Français",
      title: "francais.png",
      flag: '<svg viewBox="0 0 24 16" aria-hidden="true" focusable="false"><rect width="8" height="16" fill="#002395"/><rect x="8" width="8" height="16" fill="#fff"/><rect x="16" width="8" height="16" fill="#ED2939"/></svg>',
    },
    {
      code: "pt",
      name: "Português",
      title: "portugues.png",
      flag: '<svg viewBox="0 0 24 16" aria-hidden="true" focusable="false"><rect width="24" height="16" fill="#DA291C"/><rect width="9.6" height="16" fill="#046A38"/><circle cx="9.6" cy="8" r="3.4" fill="#FFD100"/><circle cx="9.6" cy="8" r="2" fill="#DA291C"/><rect x="8.7" y="5.5" width="1.8" height="5" rx="0.3" fill="#fff"/></svg>',
    },
    {
      code: "en",
      name: "English",
      title: "english.png",
      flag: '<svg viewBox="0 0 24 16" aria-hidden="true" focusable="false"><rect width="24" height="16" fill="#012169"/><path d="M0 0 L24 16 M24 0 L0 16" stroke="#fff" stroke-width="3.2"/><path d="M0 0 L24 16 M24 0 L0 16" stroke="#C8102E" stroke-width="1.6"/><path d="M12 0 V16 M0 8 H24" stroke="#fff" stroke-width="5.4"/><path d="M12 0 V16 M0 8 H24" stroke="#C8102E" stroke-width="3.2"/></svg>',
    },
  ];

  const CODES = LANGUAGES.map((language) => language.code);

  /* Attribute copy lives on data-i18n-<attribute>; text lives on data-i18n. */
  const ATTRIBUTES = ["aria-label", "title", "placeholder", "content", "alt"];

  const STRINGS = {
    es: {
      /* Menu chrome and status */
      languageLabel: "Idioma",
      languageChooserTitle: "Elige tu idioma",
      searchPlaceholder: "Buscar proyectos…",
      searchLabel: "Buscar proyectos",
      favorites: "Favoritos",
      favoritesCount: "Favoritos ({n})",
      refresh: "Actualizar",
      loading: "Cargando proyectos…",
      loadingShort: "Cargando…",
      found: "{n} proyectos encontrados.",
      filter: "{visible} de {total} proyectos encontrados.",
      offline: "Mostrando el último listado guardado sin conexión.",
      loadError: "No se pudo cargar la lista de proyectos. Revisa tu conexión e inténtalo de nuevo.",
      storageFailed: "No se pudo guardar este cambio en el navegador.",
      retry: "Reintentar",
      logoAlt: "Basic Engine Hub logo",
      metaDescription:
        "Menú de proyectos de Basic Engine Hub: estudio y perfil de Alvaro_Games19, reproducibles en TurboWarp.",

      /* Cards and details */
      defaultTitle: "Proyecto {id}",
      featuredBadge: "★ Destacado",
      detailsUnavailable: "Los detalles ampliados necesitan conexión o el servidor web local.",
      descriptionTitle: "Descripción",
      instructionsTitle: "Instrucciones",
      commentsTitle: "Comentarios",
      noDescription: "Sin descripción.",
      noInstructions: "Sin instrucciones.",
      commentsUnavailable: "Los comentarios no están disponibles ahora.",
      noComments: "Sin comentarios todavía.",
      detailOpenScratch: "Abrir en Scratch",
      detailClose: "Cerrar",
      detailCloseLabel: "Cerrar detalles",
      detailPlay: "Jugar",
      favoriteAdd: "Añadir a favoritos",
      favoriteRemove: "Quitar de favoritos",

      /* Player */
      playerLoading: "Cargando proyecto…",
      playerFrameTitle: "Reproductor del proyecto",
      back: "← Volver al menú",
      playerFlag: "Bandera",
      start: "Iniciar",
      pause: "Pausar",
      resume: "Reanudar",
      stop: "Detener",
      fullscreen: "Pantalla completa",
      clones: "Clones",
      cacheSaveFailed: "Proyecto cargado; el navegador no pudo guardarlo en IndexedDB.",
      playerStartFailed: "No se pudo iniciar el reproductor local.",

      /* Variables and lists */
      variablesTitle: "Variables y listas",
      thSave: "Guardar",
      saveVariableLabel: "Guardar {name}",
      thKind: "Tipo",
      thVariable: "Variable",
      thTarget: "Objetivo",
      thValue: "Valor",
      kindList: "Lista",
      kindVariable: "Variable",
      variablesEmpty: "No hay variables en este proyecto.",
      edit: "Editar",
      editValueTitle: "Editar valor",
      editListTitle: "Editar lista",
      editVariableTitle: "Editar variable",
      valueLabel: "Valor",
      cancel: "Cancelar",
      save: "Guardar",

      /* Scratch sign-in */
      signIn: "Iniciar sesión",
      signOut: "Salir",
      sessionUser: "Sesión de @{name} en este navegador",
      authTitle: "Iniciar sesión con Scratch",
      authIntro:
        "Vas a recibir un código. Escribilo en el proyecto de autenticación de Scratch (o dejalo en un comentario) y volvé a esta pestaña: la sesión se confirma sola.",
      authMethodLabel: "Método",
      authMethodCloud: "Escribir el código en el proyecto",
      authMethodComment: "Comentar el código en el proyecto",
      authMethodProfile: "Comentar el código en tu perfil",
      authUsernameLabel: "Tu usuario de Scratch",
      authUsernamePlaceholder: "usuario",
      authContinue: "Continuar",
      authCodeLabel: "Código de acceso",
      authCopy: "Copiar código",
      authOpen: "Abrir el proyecto en Scratch",
      authVerify: "Verificar",
      authChecking: "Comprobando la sesión…",
      authRequesting: "Generando tu código…",
      authWaitingProject:
        "Escribí el código en el proyecto y volvé a esta pestaña. Esperando la confirmación…",
      authWaitingComment:
        "Dejá el código en un comentario del proyecto y volvé a esta pestaña. Esperando la confirmación…",
      authWaitingProfile:
        "Dejá el código en un comentario de tu propio perfil y volvé a esta pestaña. Esperando la confirmación…",
      authUsernameRequired: "Escribí tu usuario de Scratch y tocá Continuar.",
      authCopied: "Código copiado.",
      authCopyError: "No se pudo copiar; seleccioná el código a mano.",
      authRequestFailed: "No se pudo generar el código. Revisá tu conexión e intentá de nuevo.",
      authRejected: "La confirmación no corresponde a este sitio. Se canceló el inicio de sesión.",
      authExpired: "El código venció. Cancelá y volvé a intentar.",
      authCallbackFailed: "No se pudo confirmar la sesión. Iniciá sesión de nuevo.",

      /* PenguinMod sign-in (profile bio), web only */
      authMethodPenguinMod: "Pegar el código en tu bio de PenguinMod",
      authIntroPenguinMod:
        "Vas a recibir un código. Pegalo en la bio de tu perfil de PenguinMod y volvé a esta pestaña; la leemos nosotros.",
      authWaitingPenguinMod:
        "Pegá el código en la bio de tu perfil de PenguinMod y volvé a esta pestaña. Esperando la confirmación…",
      authUsernamePenguinMod: "Tu usuario de PenguinMod",
      authUsernameRequiredPenguinMod: "Escribí tu usuario de PenguinMod y tocá Continuar.",
      authEditPenguinMod: "Editar tu bio en PenguinMod",
      authPenguinModNotFound: "No encontré ese usuario de PenguinMod, o su perfil es privado.",

      /* Player page (web/player.html), which the desktop shell embeds too */
      selectProject: "Elige un proyecto",
      errorPrefix: "Error: ",
      bundleMissing: "Falta el paquete de Scaffolding",
      noActiveClones: "Sin clones activos",
      noProject: "Sin proyecto",
      fsExit: "Salir de pantalla completa",
    },
    en: {
      /* Menu chrome and status */
      languageLabel: "Language",
      languageChooserTitle: "Choose your language",
      searchPlaceholder: "Search projects…",
      searchLabel: "Search projects",
      favorites: "Favorites",
      favoritesCount: "Favorites ({n})",
      refresh: "Refresh",
      loading: "Loading projects…",
      loadingShort: "Loading…",
      found: "{n} projects found.",
      filter: "{visible} of {total} projects found.",
      offline: "Showing the last saved listing while offline.",
      loadError: "The project list could not be loaded. Check your connection and try again.",
      storageFailed: "This change could not be saved in this browser.",
      retry: "Try again",
      logoAlt: "Basic Engine Hub logo",
      metaDescription:
        "Basic Engine Hub project menu: Alvaro_Games19's studio and profile, playable in TurboWarp.",

      /* Cards and details */
      defaultTitle: "Project {id}",
      featuredBadge: "★ Featured",
      detailsUnavailable: "Expanded details need a connection or the local web server.",
      descriptionTitle: "Description",
      instructionsTitle: "Instructions",
      commentsTitle: "Comments",
      noDescription: "No description.",
      noInstructions: "No instructions.",
      commentsUnavailable: "Comments are not available right now.",
      noComments: "No comments yet.",
      detailOpenScratch: "Open in Scratch",
      detailClose: "Close",
      detailCloseLabel: "Close details",
      detailPlay: "Play",
      favoriteAdd: "Add to favorites",
      favoriteRemove: "Remove from favorites",

      /* Player */
      playerLoading: "Loading project…",
      playerFrameTitle: "Project player",
      back: "← Back to the menu",
      playerFlag: "Flag",
      start: "Start",
      pause: "Pause",
      resume: "Resume",
      stop: "Stop",
      fullscreen: "Fullscreen",
      clones: "Clones",
      cacheSaveFailed: "Project loaded; the browser could not store it in IndexedDB.",
      playerStartFailed: "The local player could not be started.",

      /* Variables and lists */
      variablesTitle: "Variables and lists",
      thSave: "Save",
      saveVariableLabel: "Save {name}",
      thKind: "Type",
      thVariable: "Variable",
      thTarget: "Target",
      thValue: "Value",
      kindList: "List",
      kindVariable: "Variable",
      variablesEmpty: "This project has no variables.",
      edit: "Edit",
      editValueTitle: "Edit value",
      editListTitle: "Edit list",
      editVariableTitle: "Edit variable",
      valueLabel: "Value",
      cancel: "Cancel",
      save: "Save",

      /* Scratch sign-in */
      signIn: "Sign in",
      signOut: "Sign out",
      sessionUser: "Signed in as @{name} in this browser",
      authTitle: "Sign in with Scratch",
      authIntro:
        "You will get a code. Write it in the Scratch sign-in project (or leave it in a comment) and come back to this tab: the session confirms itself.",
      authMethodLabel: "Method",
      authMethodCloud: "Write the code in the project",
      authMethodComment: "Comment the code on the project",
      authMethodProfile: "Comment the code on your profile",
      authUsernameLabel: "Your Scratch username",
      authUsernamePlaceholder: "username",
      authContinue: "Continue",
      authCodeLabel: "Sign-in code",
      authCopy: "Copy code",
      authOpen: "Open the project in Scratch",
      authVerify: "Verify",
      authChecking: "Checking the session…",
      authRequesting: "Generating your code…",
      authWaitingProject:
        "Write the code in the project and come back to this tab. Waiting for confirmation…",
      authWaitingComment:
        "Leave the code in a comment on the project and come back to this tab. Waiting for confirmation…",
      authWaitingProfile:
        "Leave the code in a comment on your own profile and come back to this tab. Waiting for confirmation…",
      authUsernameRequired: "Write your Scratch username and press Continue.",
      authCopied: "Code copied.",
      authCopyError: "Could not copy; select the code by hand.",
      authRequestFailed: "The code could not be generated. Check your connection and try again.",
      authRejected: "The confirmation does not belong to this site. Sign-in was cancelled.",
      authExpired: "The code expired. Cancel and try again.",
      authCallbackFailed: "The session could not be confirmed. Sign in again.",

      /* PenguinMod sign-in (profile bio), web only */
      authMethodPenguinMod: "Paste the code in your PenguinMod bio",
      authIntroPenguinMod:
        "You will get a code. Paste it in your PenguinMod profile bio and come back to this tab; we read it back.",
      authWaitingPenguinMod:
        "Paste the code in your PenguinMod profile bio and come back to this tab. Waiting for confirmation…",
      authUsernamePenguinMod: "Your PenguinMod username",
      authUsernameRequiredPenguinMod: "Enter your PenguinMod username and press Continue.",
      authEditPenguinMod: "Edit your PenguinMod bio",
      authPenguinModNotFound: "That PenguinMod user was not found, or their profile is private.",

      /* Player page (web/player.html), which the desktop shell embeds too */
      selectProject: "Select a project",
      errorPrefix: "Error: ",
      bundleMissing: "Scaffolding bundle missing",
      noActiveClones: "No active clones",
      noProject: "No project",
      fsExit: "Exit fullscreen",
    },
    fr: {
      /* Menu chrome and status */
      languageLabel: "Langue",
      languageChooserTitle: "Choisis ta langue",
      searchPlaceholder: "Rechercher des projets…",
      searchLabel: "Rechercher des projets",
      favorites: "Favoris",
      favoritesCount: "Favoris ({n})",
      refresh: "Actualiser",
      loading: "Chargement des projets…",
      loadingShort: "Chargement…",
      found: "{n} projets trouvés.",
      filter: "{visible} sur {total} projets trouvés.",
      offline: "Affichage de la dernière liste enregistrée hors ligne.",
      loadError: "Impossible de charger la liste des projets. Vérifie ta connexion et réessaie.",
      storageFailed: "Impossible d'enregistrer ce changement dans le navigateur.",
      retry: "Réessayer",
      logoAlt: "Logo de Basic Engine Hub",
      metaDescription:
        "Menu des projets de Basic Engine Hub : studio et profil d'Alvaro_Games19, jouables dans TurboWarp.",

      /* Cards and details */
      defaultTitle: "Projet {id}",
      featuredBadge: "★ En vedette",
      detailsUnavailable:
        "Les détails complets nécessitent une connexion ou le serveur web local.",
      descriptionTitle: "Description",
      instructionsTitle: "Instructions",
      commentsTitle: "Commentaires",
      noDescription: "Pas de description.",
      noInstructions: "Pas d'instructions.",
      commentsUnavailable: "Les commentaires ne sont pas disponibles pour le moment.",
      noComments: "Pas encore de commentaires.",
      detailOpenScratch: "Ouvrir dans Scratch",
      detailClose: "Fermer",
      detailCloseLabel: "Fermer les détails",
      detailPlay: "Jouer",
      favoriteAdd: "Ajouter aux favoris",
      favoriteRemove: "Retirer des favoris",

      /* Player */
      playerLoading: "Chargement du projet…",
      playerFrameTitle: "Lecteur du projet",
      back: "← Retour au menu",
      playerFlag: "Drapeau",
      start: "Démarrer",
      pause: "Pause",
      resume: "Reprendre",
      stop: "Arrêter",
      fullscreen: "Plein écran",
      clones: "Clones",
      cacheSaveFailed: "Projet chargé ; le navigateur n'a pas pu l'enregistrer dans IndexedDB.",
      playerStartFailed: "Impossible de démarrer le lecteur local.",

      /* Variables and lists */
      variablesTitle: "Variables et listes",
      thSave: "Enregistrer",
      saveVariableLabel: "Enregistrer {name}",
      thKind: "Type",
      thVariable: "Variable",
      thTarget: "Cible",
      thValue: "Valeur",
      kindList: "Liste",
      kindVariable: "Variable",
      variablesEmpty: "Ce projet n'a pas de variables.",
      edit: "Modifier",
      editValueTitle: "Modifier la valeur",
      editListTitle: "Modifier la liste",
      editVariableTitle: "Modifier la variable",
      valueLabel: "Valeur",
      cancel: "Annuler",
      save: "Enregistrer",

      /* Scratch sign-in */
      signIn: "Se connecter",
      signOut: "Se déconnecter",
      sessionUser: "Session de @{name} dans ce navigateur",
      authTitle: "Se connecter avec Scratch",
      authIntro:
        "Tu vas recevoir un code. Écris-le dans le projet d'authentification Scratch (ou laisse-le dans un commentaire) et reviens sur cet onglet : la session se confirme toute seule.",
      authMethodLabel: "Méthode",
      authMethodCloud: "Écrire le code dans le projet",
      authMethodComment: "Commenter le code sur le projet",
      authMethodProfile: "Commenter le code sur ton profil",
      authUsernameLabel: "Ton nom d'utilisateur Scratch",
      authUsernamePlaceholder: "utilisateur",
      authContinue: "Continuer",
      authCodeLabel: "Code de connexion",
      authCopy: "Copier le code",
      authOpen: "Ouvrir le projet dans Scratch",
      authVerify: "Vérifier",
      authChecking: "Vérification de la session…",
      authRequesting: "Génération de ton code…",
      authWaitingProject:
        "Écris le code dans le projet et reviens sur cet onglet. En attente de la confirmation…",
      authWaitingComment:
        "Laisse le code dans un commentaire du projet et reviens sur cet onglet. En attente de la confirmation…",
      authWaitingProfile:
        "Laisse le code dans un commentaire de ton propre profil et reviens sur cet onglet. En attente de la confirmation…",
      authUsernameRequired: "Écris ton nom d'utilisateur Scratch et appuie sur Continuer.",
      authCopied: "Code copié.",
      authCopyError: "Impossible de copier ; sélectionne le code à la main.",
      authRequestFailed:
        "Impossible de générer le code. Vérifie ta connexion et réessaie.",
      authRejected:
        "La confirmation ne correspond pas à ce site. La connexion a été annulée.",
      authExpired: "Le code a expiré. Annule et réessaie.",
      authCallbackFailed: "Impossible de confirmer la session. Reconnecte-toi.",

      /* PenguinMod sign-in (profile bio), web only */
      authMethodPenguinMod: "Coller le code dans ta bio PenguinMod",
      authIntroPenguinMod:
        "Tu recevras un code. Colle-le dans la bio de ton profil PenguinMod et reviens sur cet onglet ; on la relira.",
      authWaitingPenguinMod:
        "Colle le code dans la bio de ton profil PenguinMod et reviens sur cet onglet. Confirmation en attente…",
      authUsernamePenguinMod: "Ton nom d'utilisateur PenguinMod",
      authUsernameRequiredPenguinMod: "Écris ton nom d'utilisateur PenguinMod et appuie sur Continuer.",
      authEditPenguinMod: "Modifier ta bio PenguinMod",
      authPenguinModNotFound: "Cet utilisateur PenguinMod est introuvable, ou son profil est privé.",

      /* Player page (web/player.html), which the desktop shell embeds too */
      selectProject: "Choisis un projet",
      errorPrefix: "Erreur : ",
      bundleMissing: "Le paquet Scaffolding est manquant",
      noActiveClones: "Aucun clone actif",
      noProject: "Aucun projet",
      fsExit: "Quitter le plein écran",
    },
    pt: {
      /* Menu chrome and status */
      languageLabel: "Idioma",
      languageChooserTitle: "Escolha seu idioma",
      searchPlaceholder: "Pesquisar projetos…",
      searchLabel: "Pesquisar projetos",
      favorites: "Favoritos",
      favoritesCount: "Favoritos ({n})",
      refresh: "Atualizar",
      loading: "Carregando projetos…",
      loadingShort: "Carregando…",
      found: "{n} projetos encontrados.",
      filter: "{visible} de {total} projetos encontrados.",
      offline: "Mostrando a última lista salva sem conexão.",
      loadError: "Não foi possível carregar a lista de projetos. Verifique sua conexão e tente de novo.",
      storageFailed: "Não foi possível salvar esta mudança no navegador.",
      retry: "Tentar de novo",
      logoAlt: "Logotipo do Basic Engine Hub",
      metaDescription:
        "Menu de projetos do Basic Engine Hub: estúdio e perfil de Alvaro_Games19, jogáveis no TurboWarp.",

      /* Cards and details */
      defaultTitle: "Projeto {id}",
      featuredBadge: "★ Destaque",
      detailsUnavailable: "Os detalhes completos precisam de conexão ou do servidor web local.",
      descriptionTitle: "Descrição",
      instructionsTitle: "Instruções",
      commentsTitle: "Comentários",
      noDescription: "Sem descrição.",
      noInstructions: "Sem instruções.",
      commentsUnavailable: "Os comentários não estão disponíveis agora.",
      noComments: "Sem comentários por enquanto.",
      detailOpenScratch: "Abrir no Scratch",
      detailClose: "Fechar",
      detailCloseLabel: "Fechar detalhes",
      detailPlay: "Jogar",
      favoriteAdd: "Adicionar aos favoritos",
      favoriteRemove: "Remover dos favoritos",

      /* Player */
      playerLoading: "Carregando projeto…",
      playerFrameTitle: "Reprodutor do projeto",
      back: "← Voltar ao menu",
      playerFlag: "Bandeira",
      start: "Iniciar",
      pause: "Pausar",
      resume: "Retomar",
      stop: "Parar",
      fullscreen: "Tela cheia",
      clones: "Clones",
      cacheSaveFailed: "Projeto carregado; o navegador não conseguiu salvá-lo no IndexedDB.",
      playerStartFailed: "Não foi possível iniciar o reprodutor local.",

      /* Variables and lists */
      variablesTitle: "Variáveis e listas",
      thSave: "Salvar",
      saveVariableLabel: "Salvar {name}",
      thKind: "Tipo",
      thVariable: "Variável",
      thTarget: "Alvo",
      thValue: "Valor",
      kindList: "Lista",
      kindVariable: "Variável",
      variablesEmpty: "Este projeto não tem variáveis.",
      edit: "Editar",
      editValueTitle: "Editar valor",
      editListTitle: "Editar lista",
      editVariableTitle: "Editar variável",
      valueLabel: "Valor",
      cancel: "Cancelar",
      save: "Salvar",

      /* Scratch sign-in */
      signIn: "Entrar",
      signOut: "Sair",
      sessionUser: "Sessão de @{name} neste navegador",
      authTitle: "Entrar com o Scratch",
      authIntro:
        "Você vai receber um código. Escreva-o no projeto de autenticação do Scratch (ou deixe-o em um comentário) e volte para esta aba: a sessão se confirma sozinha.",
      authMethodLabel: "Método",
      authMethodCloud: "Escrever o código no projeto",
      authMethodComment: "Comentar o código no projeto",
      authMethodProfile: "Comentar o código no seu perfil",
      authUsernameLabel: "Seu usuário do Scratch",
      authUsernamePlaceholder: "usuário",
      authContinue: "Continuar",
      authCodeLabel: "Código de acesso",
      authCopy: "Copiar código",
      authOpen: "Abrir o projeto no Scratch",
      authVerify: "Verificar",
      authChecking: "Verificando a sessão…",
      authRequesting: "Gerando seu código…",
      authWaitingProject:
        "Escreva o código no projeto e volte para esta aba. Aguardando a confirmação…",
      authWaitingComment:
        "Deixe o código em um comentário do projeto e volte para esta aba. Aguardando a confirmação…",
      authWaitingProfile:
        "Deixe o código em um comentário do seu próprio perfil e volte para esta aba. Aguardando a confirmação…",
      authUsernameRequired: "Escreva seu usuário do Scratch e toque em Continuar.",
      authCopied: "Código copiado.",
      authCopyError: "Não foi possível copiar; selecione o código à mão.",
      authRequestFailed:
        "Não foi possível gerar o código. Verifique sua conexão e tente de novo.",
      authRejected:
        "A confirmação não corresponde a este site. A entrada foi cancelada.",
      authExpired: "O código expirou. Cancele e tente de novo.",
      authCallbackFailed: "Não foi possível confirmar a sessão. Entre de novo.",

      /* PenguinMod sign-in (profile bio), web only */
      authMethodPenguinMod: "Colar o código na sua bio do PenguinMod",
      authIntroPenguinMod:
        "Você vai receber um código. Cole-o na bio do seu perfil do PenguinMod e volte a esta aba; nós a relermos.",
      authWaitingPenguinMod:
        "Cole o código na bio do seu perfil do PenguinMod e volte a esta aba. Aguardando a confirmação…",
      authUsernamePenguinMod: "Seu usuário do PenguinMod",
      authUsernameRequiredPenguinMod: "Escreva seu usuário do PenguinMod e toque em Continuar.",
      authEditPenguinMod: "Editar sua bio do PenguinMod",
      authPenguinModNotFound: "Esse usuário do PenguinMod não foi encontrado, ou o perfil é privado.",

      /* Player page (web/player.html), which the desktop shell embeds too */
      selectProject: "Escolha um projeto",
      errorPrefix: "Erro: ",
      bundleMissing: "O pacote Scaffolding está faltando",
      noActiveClones: "Sem clones ativos",
      noProject: "Sem projeto",
      fsExit: "Sair da tela cheia",
    },
  };

  /* The language actually in use, plus whoever wants to hear about changes. */
  const state = { lang: DEFAULT, storage: null, listeners: [] };

  function isKnownCode(code) {
    return CODES.includes(String(code));
  }

  function readStored(storage) {
    try {
      const value = storage ? storage.getItem(STORAGE_KEY) : null;
      return isKnownCode(value) ? String(value) : "";
    } catch {
      return ""; /* storage can be blocked; the site then just uses the default */
    }
  }

  /* The ?lang= the desktop shell adds to the player page, if it is a real code. */
  function requestedCode(search) {
    try {
      const value = new URLSearchParams(String(search || "").replace(/^\?/, "")).get("lang") || "";
      return isKnownCode(value) ? String(value) : "";
    } catch {
      return "";
    }
  }

  /* The query string wins (the desktop shell's contract), then the stored choice. */
  function resolveLanguage(search, storage) {
    return requestedCode(search) || readStored(storage) || DEFAULT;
  }

  /* The first-visit chooser asks only while nobody has decided: neither a stored
   * choice nor an explicit ?lang=. */
  function needsChoice(search) {
    return !readStored(state.storage) && !requestedCode(search);
  }

  /* localStorage can be blocked (private mode); the site then just uses DEFAULT. */
  function defaultStorage() {
    try {
      return typeof localStorage !== "undefined" ? localStorage : null;
    } catch {
      return null;
    }
  }

  function init(options = {}) {
    state.storage = options.storage === undefined ? defaultStorage() : options.storage;
    const search = options.search === undefined ? "" : options.search;
    state.lang = resolveLanguage(search, state.storage);
    return state.lang;
  }

  function current() {
    return state.lang;
  }

  function onChange(listener) {
    if (typeof listener === "function") state.listeners.push(listener);
  }

  /* Persist and announce a choice. An unknown code is rejected outright: it must
     never overwrite a good stored value with garbage. */
  function setLanguage(code) {
    if (!isKnownCode(code)) return DEFAULT;
    const next = String(code);
    if (next !== state.lang) {
      state.lang = next;
      try {
        if (state.storage) state.storage.setItem(STORAGE_KEY, next);
      } catch {
        /* a full or blocked storage must not stop the switch */
      }
      for (const listener of state.listeners) listener(next);
    }
    return next;
  }

  /* A missing key renders its own name, the contract uiText() already had. */
  function tr(key, params) {
    const table = STRINGS[state.lang] || STRINGS[DEFAULT] || STRINGS.es || {};
    const value = Object.prototype.hasOwnProperty.call(table, key) ? table[key] : key;
    if (!params || typeof value !== "string") return value;
    return value.replace(/\{(\w+)\}/g, (match, name) =>
      Object.prototype.hasOwnProperty.call(params, name) ? String(params[name]) : match,
    );
  }

  /* Rewrite every data-i18n hook in the document, then its language. */
  function apply(root) {
    const scope = root || (typeof document !== "undefined" ? document : null);
    if (!scope || typeof scope.querySelectorAll !== "function") return;
    for (const element of scope.querySelectorAll("[data-i18n]")) {
      element.textContent = tr(element.getAttribute("data-i18n"));
    }
    for (const attribute of ATTRIBUTES) {
      const hook = `data-i18n-${attribute}`;
      for (const element of scope.querySelectorAll(`[${hook}]`)) {
        element.setAttribute(attribute, tr(element.getAttribute(hook)));
      }
    }
    if (scope.documentElement) scope.documentElement.lang = state.lang;
  }

  const I18n = {
    STORAGE_KEY,
    DEFAULT,
    CODES,
    LANGUAGES,
    STRINGS,
    ATTRIBUTES,
    isKnownCode,
    readStored,
    requestedCode,
    resolveLanguage,
    needsChoice,
    defaultStorage,
    init,
    current,
    setLanguage,
    onChange,
    tr,
    apply,
  };

  if (typeof module !== "undefined" && module.exports) module.exports = I18n;

  /* In a browser, resolve the language and translate the static copy as soon as
   * this script runs (defer, so the document is parsed): the page never shows the
   * wrong language while app.js gets around to its first render. */
  if (typeof document !== "undefined" && typeof window !== "undefined") {
    window.I18n = I18n;
    init({ search: window.location.search });
    apply(document);
  }
})();
