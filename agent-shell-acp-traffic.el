;;; agent-shell-acp-traffic.el --- Raw ACP traffic persistence -*- lexical-binding: t; -*-

;; Copyright (C) 2024 Alvaro Ramirez

;; Author: Alvaro Ramirez https://xenodium.com
;; URL: https://github.com/xenodium/agent-shell

;; This package is free software; you can redistribute it and/or modify
;; it under the terms of the GNU General Public License as published by
;; the Free Software Foundation; either version 3, or (at your option)
;; any later version.

;; This package is distributed in the hope that it will be useful,
;; but WITHOUT ANY WARRANTY; without even the implied warranty of
;; MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
;; GNU General Public License for more details.

;; You should have received a copy of the GNU General Public License
;; along with GNU Emacs.  If not, see <https://www.gnu.org/licenses/>.

;;; Commentary:
;;
;; Persists raw ACP (Agent Client Protocol) traffic to per-agent JSONL
;; files.  Every request, response, and notification flowing through the
;; ACP client is written as a JSON line.  No enrichment is applied — the
;; raw JSON-RPC objects are preserved verbatim for ad-hoc analysis.
;;
;; Enable via:
;;
;;   (setq agent-shell-acp-traffic-enabled t)
;;
;; Files are written under `agent-shell-acp-traffic-directory', one per
;; agent binary (e.g. claude.jsonl, gemini.jsonl).

;;; Code:

(require 'json)
(require 'map)

(eval-when-compile
  (require 'cl-lib))

(defcustom agent-shell-acp-traffic-enabled nil
  "When non-nil, persist raw ACP traffic to per-agent JSONL files.
See `agent-shell-acp-traffic-directory' for the output location."
  :type 'boolean
  :group 'agent-shell)

(defcustom agent-shell-acp-traffic-directory
  (expand-file-name ".agent-shell/acp-traffic/" "~")
  "Directory for raw ACP traffic JSONL files.
Each agent binary gets its own file (e.g. claude.jsonl, gemini.jsonl)."
  :type 'directory
  :group 'agent-shell)

(defun agent-shell--acp-traffic--agent-name (client)
  "Return a display name for CLIENT's traffic file.
Prefers the agent's mode-line-name from the client's context buffer,
falls back to the ACP command name, then to \"unknown\"."
  (or (when-let* ((buf (map-elt client :context-buffer))
                  (buf-state (and (buffer-live-p buf)
                                 (buffer-local-value 'agent-shell--state buf)))
                  (agent-config (map-elt buf-state :agent-config)))
        (map-elt agent-config :mode-line-name))
      (file-name-base (or (map-elt client :command) ""))
      "unknown"))

(defun agent-shell--acp-traffic-file (client)
  "Return the JSONL file path for CLIENT's traffic."
  (let* ((name (agent-shell--acp-traffic--agent-name client))
         (filename (concat name ".jsonl"))
         (dir agent-shell-acp-traffic-directory))
    (unless (file-directory-p dir)
      (make-directory dir t))
    (expand-file-name filename dir)))

(defun agent-shell--write-acp-traffic (client direction kind message)
  "Write a raw ACP traffic entry to disk.
CLIENT, DIRECTION, KIND, and MESSAGE are the same arguments passed to
`acp--log-traffic'.  Each entry is appended as one JSON line."
  (when agent-shell-acp-traffic-enabled
    (let* ((file (agent-shell--acp-traffic-file client))
           (object (map-elt message :object))
           (entry `(:timestamp ,(format-time-string "%Y-%m-%dT%H:%M:%S%z")
                    :direction ,(symbol-name direction)
                    :kind ,(symbol-name kind)
                    :object ,object)))
      (condition-case err
          (with-temp-buffer
            (insert (json-serialize entry))
            (insert "\n")
            (write-region (point-min) (point-max) file t 'no-message))
        (error
         (message "ACP traffic write error: %S" err))))))

(with-eval-after-load 'acp
  (advice-add 'acp--log-traffic :after
              #'agent-shell--write-acp-traffic))

(provide 'agent-shell-acp-traffic)
;;; agent-shell-acp-traffic.el ends here
