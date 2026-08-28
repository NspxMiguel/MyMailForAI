(function () {
  const dictionary = {
    en: {
      btn_lang: "PT",
      hero_title: "MyMailForAI",
      hero_subtitle: "Your own mailbox, with full access for your AI agent, and the brake in the menu bar.",
      install_title: "Installation",
      install_intro: "Install via Homebrew tap and authenticate your email account:",
      comparison_title: "MailForAI vs MyMailForAI",
      th_feature: "Feature",
      th_mailforai: "MailForAI",
      th_mymailforai: "MyMailForAI",
      row_mailbox_label: "Mailbox",
      row_mailbox_mfa: "Agent's mailbox (claude@nspx.dev)",
      row_mailbox_mymfa: "Your own (Gmail, iCloud, etc.)",
      row_scope_label: "Scope",
      row_scope_mfa: "Send to allowlist only",
      row_scope_mymfa: "Read all, write, move, archive",
      row_interface_label: "Interface",
      row_interface_mfa: "Windowed app with tabs & assistant",
      row_interface_mymfa: "Menu bar item only",
      row_brake_label: "Brake",
      row_brake_mfa: "Allowlist + daily limit",
      row_brake_mymfa: "Mode (automatic / ask / read-only)",
      row_accounts_label: "Accounts",
      row_accounts_mfa: "One",
      row_accounts_mymfa: "As many as you want, with logout",
      modes_title: "Execution Modes",
      mode_auto_title: "auto (Automatic)",
      mode_auto_desc: "Read access is fully enabled, and all email sending or writing actions execute immediately.",
      mode_ask_title: "ask (Ask Permission — Default)",
      mode_ask_desc: "Read access is fully enabled; write actions enter the queue and await approval in the menu bar.",
      mode_read_title: "read (Read-Only)",
      mode_read_desc: "Read access is fully enabled, but any write or modification attempt is rejected with a clear explanation.",
      menubar_title: "Menu Bar Panel",
      menubar_intro: "The native macOS menu bar app gives you continuous visibility and instant control:",
      menubar_item_1_title: "Account overview:",
      menubar_item_1_desc: "List of connected accounts, active execution modes, and unread email counters.",
      menubar_item_2_title: "Pending queue:",
      menubar_item_2_desc: "Pending action requests with one-click Confirm or Reject buttons.",
      menubar_item_3_title: "Mode control:",
      menubar_item_3_desc: "Quick mode selector per account (automatic, ask, or read-only).",
      menubar_item_4_title: "Account management:",
      menubar_item_4_desc: "Add new email accounts, log out, switch display language, or uninstall.",
      privacy_title: "Privacy & Security",
      privacy_desc: "Your app password goes directly into the macOS Keychain. Nothing ever leaves your machine, and there is no server of ours.",
      mcp_title: "MCP Tools",
      mcp_intro: "When launched with mymailforai mcp, the following Model Context Protocol tools are exposed over stdio:",
      mcp_list_accounts: "List configured accounts, default account, and status.",
      mcp_mailbox_status: "Check inbox summary and unread mail counts.",
      mcp_list_folders: "List all folders in the mailbox.",
      mcp_list_inbox: "List recent messages from the inbox.",
      mcp_search_email: "Search emails by sender, recipient, subject, text, or date.",
      mcp_read_email: "Read complete message content and headers by UID.",
      mcp_download_attachment: "Save email attachments on demand to local disk.",
      mcp_send_email: "Send a new email message.",
      mcp_reply_email: "Reply to an existing email thread.",
      mcp_forward_email: "Forward an email to specified recipients.",
      mcp_save_draft: "Save a draft message without sending.",
      mcp_mark_email: "Mark emails as read, unread, starred, or unstarred.",
      mcp_move_email: "Move messages to a specified folder.",
      mcp_archive_email: "Move messages to the Archive folder.",
      mcp_trash_email: "Safely move messages to the Trash folder.",
      mcp_list_pending: "List actions in the queue waiting for approval."
    },
    pt: {
      btn_lang: "EN",
      hero_title: "MyMailForAI",
      hero_subtitle: "A caixa do próprio dono, com acesso total pro agente e o freio na barra de menus.",
      install_title: "Instalação",
      install_intro: "Instale via tap do Homebrew e faça login na sua conta:",
      comparison_title: "MailForAI x MyMailForAI",
      th_feature: "Recurso",
      th_mailforai: "MailForAI",
      th_mymailforai: "MyMailForAI",
      row_mailbox_label: "Caixa",
      row_mailbox_mfa: "Do agente (claude@nspx.dev)",
      row_mailbox_mymfa: "A dele (Gmail, iCloud, o que for)",
      row_scope_label: "Alcance",
      row_scope_mfa: "Enviar para quem está na allowlist",
      row_scope_mymfa: "Ler tudo, escrever, mover, arquivar",
      row_interface_label: "Interface",
      row_interface_mfa: "App com janela, abas, assistente",
      row_interface_mymfa: "Só o item da barra de menus",
      row_brake_label: "Freio",
      row_brake_mfa: "Allowlist + teto diário",
      row_brake_mymfa: "Modo (automático / pedir / só leitura)",
      row_accounts_label: "Contas",
      row_accounts_mfa: "Uma",
      row_accounts_mymfa: "Quantas ele quiser, com logout",
      modes_title: "Modos de Operação",
      mode_auto_title: "auto (Automático)",
      mode_auto_desc: "Leitura liberada, e-mails e ações de escrita são enviados imediatamente.",
      mode_ask_title: "ask (Pedir permissão — Padrão)",
      mode_ask_desc: "Leitura liberada; ações de escrita entram na fila e aguardam aprovação no painel.",
      mode_read_title: "read (Somente leitura)",
      mode_read_desc: "Leitura liberada; qualquer tentativa de escrita é recusada com motivo.",
      menubar_title: "Painel da Barra de Menus",
      menubar_intro: "O app nativo da barra de menus do macOS oferece visibilidade total e controle instantâneo:",
      menubar_item_1_title: "Visão geral das contas:",
      menubar_item_1_desc: "Lista de contas configuradas, modo de operação ativo e contagem de não lidos.",
      menubar_item_2_title: "Fila de pendências:",
      menubar_item_2_desc: "Ações aguardando aprovação com botões de Confirmar ou Recusar em um clique.",
      menubar_item_3_title: "Controle de modo:",
      menubar_item_3_desc: "Seletor rápido de modo por conta (automático, pedir permissão ou somente leitura).",
      menubar_item_4_title: "Gestão de contas:",
      menubar_item_4_desc: "Adicionar novas contas de e-mail, sair, trocar idioma ou desinstalar.",
      privacy_title: "Privacidade e Segurança",
      privacy_desc: "A senha de aplicativo vai pro Chaveiro do macOS, nada sai da máquina, não existe servidor nosso.",
      mcp_title: "Ferramentas MCP",
      mcp_intro: "Ao executar com mymailforai mcp, as seguintes ferramentas do Model Context Protocol ficam disponíveis via stdio:",
      mcp_list_accounts: "Lista contas configuradas, conta padrão e status.",
      mcp_mailbox_status: "Verifica resumo da caixa de entrada e contagem de não lidos.",
      mcp_list_folders: "Lista as pastas da caixa de e-mail.",
      mcp_list_inbox: "Lista mensagens recentes da caixa de entrada.",
      mcp_search_email: "Busca e-mails por remetente, destinatário, assunto, texto ou data.",
      mcp_read_email: "Lê o conteúdo completo e cabeçalhos de um e-mail por UID.",
      mcp_download_attachment: "Baixa anexos de e-mail sob demanda para o disco.",
      mcp_send_email: "Envia uma nova mensagem de e-mail.",
      mcp_reply_email: "Responde a uma thread de e-mail existente.",
      mcp_forward_email: "Encaminha um e-mail para destinatários.",
      mcp_save_draft: "Salva um rascunho de mensagem sem enviar.",
      mcp_mark_email: "Marca mensagens como lidas, não lidas, com estrela ou sem estrela.",
      mcp_move_email: "Move mensagens para uma pasta específica.",
      mcp_archive_email: "Move mensagens para a pasta Arquivo.",
      mcp_trash_email: "Move mensagens para a Lixeira com segurança.",
      mcp_list_pending: "Lista a fila de ações aguardando aprovação."
    }
  };

  function getInitialLang() {
    const saved = localStorage.getItem("mymailforai_lang");
    if (saved === "pt" || saved === "en") {
      return saved;
    }
    const navLang = (navigator.language || navigator.userLanguage || "").toLowerCase();
    if (navLang.startsWith("pt")) {
      return "pt";
    }
    return "en";
  }

  let currentLang = getInitialLang();

  function applyLanguage(lang) {
    currentLang = lang;
    localStorage.setItem("mymailforai_lang", lang);
    document.documentElement.lang = lang;

    const dict = dictionary[lang] || dictionary.en;

    document.querySelectorAll("[data-i18n]").forEach((el) => {
      const key = el.getAttribute("data-i18n");
      if (dict[key] !== undefined) {
        el.textContent = dict[key];
      }
    });

    const btn = document.getElementById("lang-btn");
    if (btn) {
      btn.textContent = dict.btn_lang;
    }
  }

  window.i18nToggle = function () {
    const newLang = currentLang === "pt" ? "en" : "pt";
    applyLanguage(newLang);
  };

  window.i18n = {
    dictionary,
    setLanguage: applyLanguage,
    getCurrentLanguage: () => currentLang
  };

  document.addEventListener("DOMContentLoaded", () => {
    applyLanguage(currentLang);
  });
})();
