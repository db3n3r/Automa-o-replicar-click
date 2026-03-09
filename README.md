# Automa-o-replicar-click


Gravador e reprodutor de macros para Windows com interface gráfica.  
Grava cliques, movimentos do mouse, scroll e teclas (incluindo combinações como Ctrl+C, Ctrl+V, Alt+Tab) e reproduz tudo com fidelidade.

---

## Recursos

| Recurso | Descrição |
|---------|-----------|
| **Interface gráfica** | Janela compacta (always-on-top) com botões de gravar, reproduzir e parar |
| **Atalhos globais** | F9 (gravar), F10 (reproduzir), F11 (parar) — funcionam mesmo com a janela minimizada |
| **Combinações de tecla** | Grava key_down / key_up separadamente, reproduzindo fielmente Ctrl+C, Ctrl+V, Alt+Tab, Shift+seleção, etc. |
| **Mouse preciso** | Usa Win32 `SetCursorPos` / `GetCursorPos` com DPI-awareness para coordenadas exatas |
| **Scroll fiel** | Reproduz scroll via Win32 `mouse_event` com `WHEEL_DELTA` nativo |
| **Filtro de movimentos** | Ignora micro-movimentos (< 3 px / < 15 ms) para evitar milhares de eventos inúteis |
| **Velocidade** | Reprodução de 0.25x a 8x |
| **Repetições** | Número configurável de repetições ou loop infinito |
| **Salvar / Abrir** | Exporta e importa macros em formato JSON |
| **Lista de eventos** | Tabela com todos os eventos gravados (tipo, detalhe, tempo) |

---

## Pré-requisitos

- **Python 3.10+**
- **Windows** (usa APIs Win32 para precisão de mouse e scroll)

### Dependências

```bash
pip install pyautogui keyboard mouse
```

| Pacote | Versão mínima | Uso |
|--------|---------------|-----|
| `pyautogui` | 0.9+ | Cliques de mouse (mouseDown/mouseUp) |
| `keyboard` | 0.13+ | Hook global de teclado, key_down/key_up na reprodução |
| `mouse` | 0.7+ | Hook global de mouse (move, click, scroll) |

> Todas as três bibliotecas são **pure-Python** com extensões C mínimas e podem ser instaladas via pip.

---

## Como usar

### 1. Executar

```bash
python chamados.py
```

A janela do Macro Recorder abrirá imediatamente.

### 2. Gravar uma macro

1. Clique em **⏺ Gravar** ou pressione **F9**.
2. Execute as ações que deseja gravar (cliques, digitação, scroll, etc.).
3. Pressione **F11** ou **ESC** para parar a gravação.
4. Os eventos aparecerão na lista e serão salvos automaticamente em `events.json`.

### 3. Reproduzir uma macro

1. Ajuste a **velocidade** (1.0x = velocidade original).
2. Defina o número de **repetições** ou marque **Loop infinito**.
3. Clique em **▶ Reproduzir** ou pressione **F10**.
4. Para interromper, pressione **F11** ou clique em **⏹ Parar**.

### 4. Gerenciar arquivos

- **Salvar como…** — salva a macro atual em um novo arquivo `.json`.
- **Abrir…** — carrega uma macro de um arquivo `.json` existente.

---

## Atalhos de teclado

| Tecla | Ação |
|-------|------|
| `F9`  | Iniciar / parar gravação |
| `F10` | Iniciar reprodução |
| `F11` | Parar gravação ou reprodução |
| `ESC` | Parar gravação (durante gravação) |

> **Dica de segurança:** mova o cursor para o **canto superior-esquerdo** da tela para ativar o fail-safe do pyautogui e abortar a reprodução em caso de emergência.

---

## Formato do arquivo de eventos (`events.json`)

O arquivo é um array JSON onde cada objeto representa um evento:

### Tipos de evento

#### `key_down` / `key_up`
```json
{
    "type": "key_down",
    "key": "ctrl",
    "scan_code": 29,
    "time": 1.234
}
```
Gravar down/up separadamente permite reproduzir combinações de tecla com fidelidade.

#### `mouse_click`
```json
{
    "type": "mouse_click",
    "x": 500,
    "y": 300,
    "button": "left",
    "pressed": true,
    "time": 2.456
}
```

#### `mouse_move`
```json
{
    "type": "mouse_move",
    "x": 512,
    "y": 310,
    "time": 2.500
}
```

#### `mouse_scroll`
```json
{
    "type": "mouse_scroll",
    "x": 500,
    "y": 300,
    "delta": -3,
    "time": 3.789
}
```
O campo `delta` é positivo para scroll para cima e negativo para baixo. Na reprodução é multiplicado por `WHEEL_DELTA` (120) da API Win32.

---

## Detalhes técnicos

### Precisão do mouse
- Chama `SetProcessDPIAware()` na inicialização para evitar escalonamento de DPI.
- Usa `GetCursorPos()` (Win32) para leitura de posição e `SetCursorPos()` para posicionamento durante reprodução — precisão de pixel.

### Precisão do scroll
- O scroll é reproduzido via `mouse_event(MOUSEEVENTF_WHEEL, ...)` diretamente pela API Win32.
- O `dwData` é calculado como `delta × WHEEL_DELTA (120)`, garantindo que cada "notch" do scroll seja reproduzido com a mesma magnitude do original.

### Teclado — combinações
- Eventos de tecla são gravados como `key_down` (pressionar) e `key_up` (soltar), não como "key_press".
- Na reprodução, usa `keyboard.press()` e `keyboard.release()`, que enviam scan codes de baixo nível.
- Isso permite reproduzir qualquer combinação: Ctrl+C, Ctrl+V, Ctrl+Shift+S, Alt+Tab, Win+D, etc.

### Filtro de movimentos do mouse
- Movimentos menores que **3 pixels** de distância são ignorados.
- Intervalo mínimo de **15 ms** entre movimentos gravados.
- Opção na interface para desativar completamente a gravação de movimentos.

### Threading
- A gravação roda na thread principal via hooks do sistema operacional.
- A reprodução roda em uma **thread daemon** separada para não travar a interface.
- O sleep durante reprodução é feito em fatias de **10 ms** para permitir parada rápida.

### Compatibilidade
- Compatível com eventos antigos do formato `key_press` (gravados por versões anteriores).
- Funciona em monitores com diferentes configurações de DPI/escala.

---

## Estrutura do projeto

```
.
├── chamados.py      # Aplicação principal (GUI + gravação + reprodução)
├── events.json      # Arquivo de macro gerado/carregado (criado automaticamente)
└── README.md        # Este arquivo
```

---

## Resolução de problemas

| Problema | Solução |
|----------|---------|
| Erro de permissão ao gravar teclas | Execute como **Administrador** |
| Coordenadas de mouse deslocadas | Verifique se a escala de exibição do Windows está em 100%, ou se o DPI-awareness está ativo |
| Scroll não funciona | Certifique-se de que o cursor está sobre a janela-alvo durante a reprodução |
| A janela some durante reprodução | A janela é "always-on-top", mas pode ser coberta por janelas fullscreen |

---

## Licença

Este projeto é distribuído livremente para uso pessoal e educacional.

