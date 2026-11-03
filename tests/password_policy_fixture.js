// Independent expected policy for browser-controller tests. Rendered-page tests
// also run against the actual rules emitted by Flask.
module.exports = [
    { key: 'length', minimum: 8, message: 'Password must be at least 8 characters.' },
    { key: 'uppercase', pattern: '[A-Z]', message: 'Password must contain at least one uppercase letter.' },
    { key: 'lowercase', pattern: '[a-z]', message: 'Password must contain at least one lowercase letter.' },
    { key: 'number', pattern: '[0-9]', message: 'Password must contain at least one number.' },
    { key: 'special', pattern: String.raw`[\x21-\x2f\x3a-\x40\x5b-\x60\x7b-\x7e]`,
      message: 'Password must contain at least one special character.' },
];
