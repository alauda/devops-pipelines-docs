# Alauda DevOps Pipelines Docs

This repository contains the documentation for the Alauda DevOps Pipelines Operator.

## Getting Started

### Prerequisites

Before you begin, make sure you have the following installed on your system:

- **[Node.js](https://nodejs.org/en/)** (version 14 or higher recommended)
- **[npm](https://www.npmjs.com/)** (comes with Node.js)
- **[Yarn](https://yarnpkg.com/)** package manager

### Installation

1. Clone this repository and navigate to the project directory
2. Install project dependencies:

```bash
yarn install
```

### Recommended Development Setup

For the best development experience, we recommend:

- **Editor**: [Visual Studio Code](https://code.visualstudio.com/)
- **Extension**: [MDX extension](https://marketplace.visualstudio.com/items?itemName=unifiedjs.vscode-mdx) for enhanced markdown editing

## Development Commands

| Command | Description |
|---------|-------------|
| `yarn dev` | Start development server with hot reload |
| `yarn build` | Build production-ready static files |
| `yarn serve` | Preview built files locally |

### Development Workflow

1. **Start development**: Run `yarn dev` to launch the local server
2. **Edit content**: Make changes to your markdown files - they'll update automatically
3. **Navigation changes**: If you modify the sidebar navigation, restart the development server
4. **Preview production**: Use `yarn build` followed by `yarn serve` to test the final build

> **💡 Tip**: The development server supports hot reloading for most changes, making your workflow smooth and efficient!
