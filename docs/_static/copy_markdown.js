/**
 * Copy as Markdown functionality for Sphinx documentation
 *
 * Adds a "Copy as Markdown" button at the top of each documentation page
 * that converts RST content to Markdown format for use with AI tools.
 */

(function () {
    'use strict';

    /**
     * Get page metadata for the markdown output
     */
    function getPageMetadata() {
        return `**Source**: ${window.location.href}\n\n---\n\n`;
    }

    /**
     * Convert RST/HTML content to Markdown format
     * This is a best-effort conversion that handles common RST elements
     */
    function convertToMarkdown() {
        const article = document.querySelector('article[role="main"]');
        if (!article) return '';

        // Clone to avoid modifying the DOM
        const clone = article.cloneNode(true);

        // Remove elements we don't want in the output
        const elementsToRemove = [
            '.headerlink',              // Remove header links
            '.copybutton',              // Remove copy buttons from code
            'button.copybtn',           // Remove any copy buttons
            '.o-tooltip--copied',       // Remove tooltip elements
            'nav',                      // Remove navigation
            '.toctree-wrapper',         // Remove TOC widgets
            'script',                   // Remove scripts
            'style',                    // Remove styles
            '#copy-markdown-container', // Remove the copy button container
            '.viewcode-link',           // Remove source code links
            '.viewcode-back'            // Remove back links
        ];

        elementsToRemove.forEach(selector => {
            clone.querySelectorAll(selector).forEach(el => el.remove());
        });

        let markdown = '';

        // Process child nodes recursively
        function processNode(node, listDepth = 0, inlineContext = false) {
            const tag = node.tagName ? node.tagName.toLowerCase() : null;

            // Handle text nodes
            if (node.nodeType === Node.TEXT_NODE) {
                if (inlineContext) {
                    // Preserve whitespace in inline context
                    return node.textContent;
                }
                const text = node.textContent.trim();
                return text || '';
            }

            // Handle element nodes
            switch (tag) {
                case 'h1':
                    return '\n# ' + node.textContent.trim() + '\n\n';
                case 'h2':
                    return '\n## ' + node.textContent.trim() + '\n\n';
                case 'h3':
                    return '\n### ' + node.textContent.trim() + '\n\n';
                case 'h4':
                    return '\n#### ' + node.textContent.trim() + '\n\n';
                case 'h5':
                    return '\n##### ' + node.textContent.trim() + '\n\n';
                case 'h6':
                    return '\n###### ' + node.textContent.trim() + '\n\n';
                case 'p':
                    // Process inline elements within paragraphs
                    let pContent = '';
                    node.childNodes.forEach(child => {
                        pContent += processNode(child, listDepth, true);
                    });
                    return pContent.trim() + '\n\n';
                case 'code':
                    // Check if it's part of a pre block (already handled)
                    if (node.parentElement && node.parentElement.tagName === 'PRE') {
                        return '';
                    }
                    return '`' + node.textContent + '`';
                case 'pre':
                    const codeBlock = node.querySelector('code');
                    if (codeBlock) {
                        // Try to extract language from class (Sphinx uses highlight-<lang>)
                        let language = '';
                        const classList = Array.from(codeBlock.classList);

                        // Check for Sphinx highlight classes
                        const highlightClass = classList.find(cls =>
                            cls.startsWith('highlight-') ||
                            cls.startsWith('language-')
                        );

                        if (highlightClass) {
                            language = highlightClass
                                .replace('highlight-', '')
                                .replace('language-', '')
                                .replace('default', 'python');  // Sphinx defaults to Python
                        }

                        // Also check parent div for language info
                        if (!language && node.parentElement) {
                            const parentClass = Array.from(node.parentElement.classList).find(cls =>
                                cls.startsWith('highlight-')
                            );
                            if (parentClass) {
                                language = parentClass.replace('highlight-', '');
                            }
                        }

                        return '\n```' + language + '\n' + codeBlock.textContent + '```\n\n';
                    }
                    return '\n```\n' + node.textContent + '```\n\n';
                case 'a':
                    const href = node.getAttribute('href');
                    let text = '';
                    node.childNodes.forEach(child => {
                        text += processNode(child, listDepth, true);
                    });
                    text = text.trim();

                    if (href && href !== '#' && !href.startsWith('#')) {
                        // Make relative URLs absolute
                        const absoluteHref = href.startsWith('http') ? href :
                            new URL(href, window.location.origin + window.location.pathname).href;
                        return '[' + text + '](' + absoluteHref + ')';
                    }
                    return text;
                case 'strong':
                case 'b':
                    let strongText = '';
                    node.childNodes.forEach(child => {
                        strongText += processNode(child, listDepth, true);
                    });
                    return '**' + strongText.trim() + '**';
                case 'em':
                case 'i':
                    let emText = '';
                    node.childNodes.forEach(child => {
                        emText += processNode(child, listDepth, true);
                    });
                    return '*' + emText.trim() + '*';
                case 'ul':
                case 'ol':
                    let list = listDepth === 0 ? '\n' : '';
                    const items = node.querySelectorAll(':scope > li');
                    const indent = '  '.repeat(listDepth);

                    items.forEach((item, index) => {
                        const prefix = tag === 'ul' ? '- ' : `${index + 1}. `;
                        list += indent + prefix;

                        // Process list item content, handling nested lists
                        let itemContent = '';
                        item.childNodes.forEach(child => {
                            if (child.tagName && (child.tagName.toLowerCase() === 'ul' || child.tagName.toLowerCase() === 'ol')) {
                                // Handle nested list
                                itemContent += '\n' + processNode(child, listDepth + 1, false);
                            } else {
                                itemContent += processNode(child, listDepth, true);
                            }
                        });

                        // Clean up and indent multi-line content
                        itemContent = itemContent.trim();
                        if (itemContent.includes('\n')) {
                            const lines = itemContent.split('\n');
                            list += lines[0] + '\n';
                            for (let i = 1; i < lines.length; i++) {
                                list += indent + '  ' + lines[i] + '\n';
                            }
                        } else {
                            list += itemContent + '\n';
                        }
                    });

                    return list + (listDepth === 0 ? '\n' : '');
                case 'li':
                    // Handled in ul/ol to manage indentation properly
                    return '';
                case 'blockquote':
                    const lines = node.textContent.trim().split('\n');
                    return '\n' + lines.map(line => '> ' + line).join('\n') + '\n\n';
                case 'table':
                    // Basic table support
                    let table = '\n';
                    const headers = Array.from(node.querySelectorAll('thead th')).map(th => th.textContent.trim());
                    const rows = Array.from(node.querySelectorAll('tbody tr'));

                    if (headers.length > 0) {
                        table += '| ' + headers.join(' | ') + ' |\n';
                        table += '| ' + headers.map(() => '---').join(' | ') + ' |\n';
                    }

                    rows.forEach(row => {
                        const cells = Array.from(row.querySelectorAll('td')).map(td => td.textContent.trim());
                        table += '| ' + cells.join(' | ') + ' |\n';
                    });

                    return table + '\n';
                case 'div':
                    // Handle special div classes (admonitions, notes, etc.)
                    if (node.classList.contains('admonition') ||
                        node.classList.contains('note') ||
                        node.classList.contains('warning') ||
                        node.classList.contains('tip') ||
                        node.classList.contains('important') ||
                        node.classList.contains('caution')) {

                        const title = node.querySelector('.admonition-title');
                        let type = 'Note';

                        // Determine admonition type
                        if (node.classList.contains('warning')) type = 'Warning';
                        else if (node.classList.contains('tip')) type = 'Tip';
                        else if (node.classList.contains('important')) type = 'Important';
                        else if (node.classList.contains('caution')) type = 'Caution';
                        else if (title) type = title.textContent.trim();

                        // Get content (everything except title)
                        const contentClone = node.cloneNode(true);
                        const titleEl = contentClone.querySelector('.admonition-title');
                        if (titleEl) titleEl.remove();

                        // Process content
                        let content = '';
                        contentClone.childNodes.forEach(child => {
                            content += processNode(child, listDepth, false);
                        });

                        // Format as blockquote
                        const lines = content.trim().split('\n');
                        let blockquote = '\n> **' + type + '**\n>\n';
                        lines.forEach(line => {
                            blockquote += '> ' + line + '\n';
                        });

                        return blockquote + '\n';
                    }

                    // Recursively process children
                    let result = '';
                    node.childNodes.forEach(child => {
                        result += processNode(child, listDepth, inlineContext);
                    });
                    return result;
                case 'section':
                    // Process section children
                    let sectionContent = '';
                    node.childNodes.forEach(child => {
                        sectionContent += processNode(child, listDepth, false);
                    });
                    return sectionContent;
                case 'dd':
                    let ddContent = '';
                    node.childNodes.forEach(child => {
                        ddContent += processNode(child, listDepth, true);
                    });
                    return '  ' + ddContent.trim().replace(/\n/g, '\n  ') + '\n';
                case 'dt':
                    let dtContent = '';
                    node.childNodes.forEach(child => {
                        dtContent += processNode(child, listDepth, true);
                    });
                    return '\n**' + dtContent.trim() + '**\n';
                case 'dl':
                    let dl = '\n';
                    node.childNodes.forEach(child => {
                        dl += processNode(child, listDepth, false);
                    });
                    return dl + '\n';
                case 'span':
                    // Process inline spans (may contain code, emphasis, etc.)
                    let spanContent = '';
                    node.childNodes.forEach(child => {
                        spanContent += processNode(child, listDepth, true);
                    });
                    return spanContent;
                case 'br':
                    return inlineContext ? '  \n' : '\n';
                case 'hr':
                    return '\n---\n\n';
                default:
                    // For unknown elements, process children
                    if (node.childNodes && node.childNodes.length > 0) {
                        let content = '';
                        node.childNodes.forEach(child => {
                            content += processNode(child, listDepth, inlineContext);
                        });
                        return content;
                    }
                    return '';
            }
        }

        // Process the entire article
        Array.from(clone.childNodes).forEach(node => {
            markdown += processNode(node);
        });

        // Clean up excessive newlines (but preserve code block spacing)
        markdown = markdown.replace(/\n{4,}/g, '\n\n\n');
        markdown = markdown.replace(/\n{3}(?!```)/g, '\n\n');
        markdown = markdown.trim();

        // Add page metadata at the top
        return getPageMetadata() + markdown;
    }

    /**
     * Copy text to clipboard
     */
    async function copyToClipboard(text) {
        try {
            await navigator.clipboard.writeText(text);
            return true;
        } catch (err) {
            // Fallback for older browsers
            const textarea = document.createElement('textarea');
            textarea.value = text;
            textarea.style.position = 'fixed';
            textarea.style.opacity = '0';
            document.body.appendChild(textarea);
            textarea.select();
            try {
                document.execCommand('copy');
                document.body.removeChild(textarea);
                return true;
            } catch (e) {
                document.body.removeChild(textarea);
                return false;
            }
        }
    }

    /**
     * Create and insert the copy button
     */
    function createCopyButton() {
        // Only show on usage pages
        const currentPath = window.location.pathname;
        if (!currentPath.includes('/usage/')) {
            return;
        }

        const article = document.querySelector('article[role="main"]');
        if (!article) return;

        // Check if button already exists
        if (document.getElementById('copy-markdown-btn')) return;

        // Create button container
        const container = document.createElement('div');
        container.id = 'copy-markdown-container';

        // Create the copy button
        const button = document.createElement('button');
        button.id = 'copy-markdown-btn';
        button.innerHTML = `
            <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor" style="vertical-align: text-bottom; margin-right: 0.3rem;">
                <path d="M0 6.75C0 5.784.784 5 1.75 5h1.5a.75.75 0 0 1 0 1.5h-1.5a.25.25 0 0 0-.25.25v7.5c0 .138.112.25.25.25h7.5a.25.25 0 0 0 .25-.25v-1.5a.75.75 0 0 1 1.5 0v1.5A1.75 1.75 0 0 1 9.25 16h-7.5A1.75 1.75 0 0 1 0 14.25Z"></path>
                <path d="M5 1.75C5 .784 5.784 0 6.75 0h7.5C15.216 0 16 .784 16 1.75v7.5A1.75 1.75 0 0 1 14.25 11h-7.5A1.75 1.75 0 0 1 5 9.25Zm1.75-.25a.25.25 0 0 0-.25.25v7.5c0 .138.112.25.25.25h7.5a.25.25 0 0 0 .25-.25v-7.5a.25.25 0 0 0-.25-.25Z"></path>
            </svg>
            Copy as Markdown
        `;
        button.title = 'Copy this page as Markdown for use with AI tools';

        // Click handler
        button.addEventListener('click', async function () {
            const originalText = this.innerHTML;
            const originalClasses = Array.from(this.classList);

            // Show loading state
            this.innerHTML = `
                <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor" style="vertical-align: text-bottom; margin-right: 0.3rem; animation: spin 1s linear infinite;">
                    <path d="M8 0a8 8 0 0 0-8 8 8 8 0 0 0 16 0 8 8 0 0 0-8-8zm0 14a6 6 0 0 1 0-12 6 6 0 0 1 0 12z" opacity="0.3"/>
                    <path d="M14 8a6 6 0 0 0-6-6V0a8 8 0 0 1 8 8z"/>
                </svg>
                Converting...
            `;
            this.classList.add('loading');
            this.disabled = true;

            try {
                const markdown = convertToMarkdown();

                if (!markdown || markdown.length === 0) {
                    throw new Error('No content to copy');
                }

                const success = await copyToClipboard(markdown);

                if (success) {
                    // Show success feedback
                    this.innerHTML = `
                        <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor" style="vertical-align: text-bottom; margin-right: 0.3rem;">
                            <path d="M13.78 4.22a.75.75 0 0 1 0 1.06l-7.25 7.25a.75.75 0 0 1-1.06 0L2.22 9.28a.751.751 0 0 1 .018-1.042.751.751 0 0 1 1.042-.018L6 10.94l6.72-6.72a.75.75 0 0 1 1.06 0Z"></path>
                        </svg>
                        Copied ${Math.round(markdown.length / 1000)}KB!
                    `;
                    this.classList.remove('loading');
                    this.classList.add('success');

                    // Reset after 2 seconds
                    setTimeout(() => {
                        this.innerHTML = originalText;
                        this.className = originalClasses.join(' ');
                        this.disabled = false;
                    }, 2000);
                } else {
                    throw new Error('Clipboard API failed');
                }
            } catch (err) {
                console.error('Copy as Markdown error:', err);

                // Show error feedback
                this.innerHTML = `
                    <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor" style="vertical-align: text-bottom; margin-right: 0.3rem;">
                        <path d="M3.72 3.72a.75.75 0 0 1 1.06 0L8 6.94l3.22-3.22a.749.749 0 0 1 1.275.326.749.749 0 0 1-.215.734L9.06 8l3.22 3.22a.749.749 0 0 1-.326 1.275.749.749 0 0 1-.734-.215L8 9.06l-3.22 3.22a.751.751 0 0 1-1.042-.018.751.751 0 0 1-.018-1.042L6.94 8 3.72 4.78a.75.75 0 0 1 0-1.06Z"></path>
                    </svg>
                    ${err.message || 'Failed to copy'}
                `;
                this.classList.remove('loading');
                this.classList.add('error');

                // Reset after 2 seconds
                setTimeout(() => {
                    this.innerHTML = originalText;
                    this.className = originalClasses.join(' ');
                    this.disabled = false;
                }, 2000);
            }
        });

        container.appendChild(button);

        // Insert at the top of the article, after the h1
        const firstHeading = article.querySelector('h1, section > h1');
        if (firstHeading) {
            firstHeading.parentNode.insertBefore(container, firstHeading.nextSibling);
        } else {
            article.insertBefore(container, article.firstChild);
        }
    }

    // Initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', createCopyButton);
    } else {
        createCopyButton();
    }

    // Re-initialize on navigation (for single-page apps or dynamic content)
    if (window.MutationObserver) {
        const observer = new MutationObserver(function (mutations) {
            mutations.forEach(function (mutation) {
                if (mutation.addedNodes.length) {
                    createCopyButton();
                }
            });
        });

        observer.observe(document.body, {
            childList: true,
            subtree: true
        });
    }
})();
