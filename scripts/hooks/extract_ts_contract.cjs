#!/usr/bin/env node
// Bounded static contract extraction: no frontend code is executed.
const fs = require('node:fs')
const path = require('node:path')
const [clientPath, typesPath] = process.argv.slice(2)
const ts = require(require.resolve('typescript', { paths: [path.dirname(clientPath)] }))
const overrides = JSON.parse(fs.readFileSync(0, 'utf8') || '{}')
const host = ts.createCompilerHost({})
const originalReadFile = host.readFile
host.readFile = file => Object.hasOwn(overrides, file) ? overrides[file] : originalReadFile(file)
const program = ts.createProgram([clientPath, typesPath], { noResolve: true, noLib: true }, host)
const checker = program.getTypeChecker()
const result = { requests: [], interfaces: {}, unions: {}, errors: [] }

function resolve(node, seen = new Set()) {
  if (!node || seen.has(node)) throw new Error('Cannot resolve URL expression')
  seen = new Set(seen).add(node)
  if (ts.isStringLiteralLike(node)) return node.text
  if (ts.isParenthesizedExpression(node)) return resolve(node.expression, seen)
  if (ts.isIdentifier(node)) {
    const declaration = checker.getSymbolAtLocation(node)?.valueDeclaration
    if (declaration && ts.isVariableDeclaration(declaration) && declaration.initializer) {
      return resolve(declaration.initializer, seen)
    }
    if (declaration && ts.isParameter(declaration)) return '{}'
    throw new Error(`Cannot resolve identifier ${node.text}`)
  }
  if (ts.isTemplateExpression(node)) {
    let value = node.head.text
    for (const span of node.templateSpans) {
      if (value.includes('?')) return value.split('?')[0] + '?'
      value += resolve(span.expression, seen) + span.literal.text
    }
    return value
  }
  if (ts.isConditionalExpression(node)) {
    const left = resolve(node.whenTrue, seen)
    const right = resolve(node.whenFalse, seen)
    if ([left, right].every(value => value === '' || value.startsWith('?'))) return '?'
    if (left === right) return left
    throw new Error('Conditional URL paths require explicit contract support')
  }
  if (ts.isBinaryExpression(node) && node.operatorToken.kind === ts.SyntaxKind.PlusToken) {
    const left = resolve(node.left, seen)
    return left.includes('?') ? left : left + resolve(node.right, seen)
  }
  if (ts.isNewExpression(node) && node.expression.getText() === 'URL') return resolve(node.arguments[0], seen)
  if (ts.isCallExpression(node)) {
    if (node.expression.getText() === 'encodeURIComponent') return '{}'
    if (ts.isPropertyAccessExpression(node.expression) && node.expression.name.text === 'toString') {
      return resolve(node.expression.expression, seen)
    }
  }
  if (ts.isPropertyAccessExpression(node)) return '{}'
  throw new Error(`Unsupported URL expression: ${node.getText()}`)
}

const client = program.getSourceFile(clientPath)
const types = program.getSourceFile(typesPath)
for (const file of [client, types]) {
  if (!file) throw new Error('Missing TypeScript source file')
  for (const diagnostic of file.parseDiagnostics) {
    result.errors.push(ts.flattenDiagnosticMessageText(diagnostic.messageText, '\n'))
  }
}
const functions = []
for (const statement of client.statements) {
  if (!statement.modifiers?.some(m => m.kind === ts.SyntaxKind.ExportKeyword)) continue
  if (ts.isFunctionDeclaration(statement)) functions.push({ name: statement.name.text, body: statement.body })
  if (ts.isVariableStatement(statement)) {
    for (const declaration of statement.declarationList.declarations) {
      const value = declaration.initializer
      if (value && (ts.isArrowFunction(value) || ts.isFunctionExpression(value))) {
        functions.push({ name: declaration.name.getText(), body: value.body })
      }
    }
  }
}
for (const fn of functions) {
  let found = false
  function visit(node) {
    const call = ts.isCallExpression(node)
    const eventSource = ts.isNewExpression(node) && node.expression.getText() === 'EventSource'
    if ((call && ['fetch', 'fetchJSON', 'fetchWithRetry', 'fetchWithDeduplication'].includes(node.expression.getText())) || eventSource) {
      found = true
      const line = client.getLineAndCharacterOfPosition(node.getStart()).line + 1
      try {
        let method = 'GET'
        if (call && node.expression.getText() !== 'fetchJSON' && node.arguments[1]) {
          const options = node.arguments[1]
          if (!ts.isObjectLiteralExpression(options)) throw new Error('Request options must be an object literal')
          for (const property of options.properties) {
            if (ts.isSpreadAssignment(property)) throw new Error('Request option spreads require explicit contract support')
            if (property.name?.getText().replace(/['"]/g, '') === 'method') {
              if (!ts.isPropertyAssignment(property)) throw new Error('Unsupported HTTP method expression')
              method = resolve(property.initializer).toUpperCase()
            }
          }
        }
        const route = resolve(node.arguments[0]).split(/[?#]/)[0]
        if (!route.startsWith('/api/')) throw new Error(`Expected an /api/ URL, got ${route}`)
        result.requests.push({ method, path: route, function: fn.name, line })
      } catch (error) {
        result.errors.push(`${fn.name}:${line}: ${error.message}`)
      }
    }
    ts.forEachChild(node, visit)
  }
  if (fn.body) visit(fn.body)
  if (!found) result.errors.push(`${fn.name}: exported client function has no recognized HTTP call`)
}
for (const node of types.statements) {
  if (ts.isInterfaceDeclaration(node)) {
    result.interfaces[node.name.text] = node.members.filter(ts.isPropertySignature).map(member => member.name.getText().replace(/['"]/g, ''))
  }
  if (ts.isTypeAliasDeclaration(node) && ts.isUnionTypeNode(node.type)) {
    const members = node.type.types
    if (members.every(member => ts.isLiteralTypeNode(member) && ts.isStringLiteral(member.literal))) {
      result.unions[node.name.text] = members.map(member => member.literal.text)
    }
  }
}
process.stdout.write(JSON.stringify(result))
