// Rules are rendered from the same definition used for server validation.
const RosaGoPasswordPolicy = (() => {
    function create(input) {
        const rules = JSON.parse(document.getElementById('password-help').getAttribute('data-password-rules'));
        const met = rule => 'minimum' in rule
            ? Array.from(input.value).length >= rule.minimum
            : new RegExp(rule.pattern, 'u').test(input.value);
        return {
            message() { return rules.find(rule => !met(rule))?.message || ''; },
            update() {
                for (const rule of rules) {
                    const satisfied = met(rule);
                    document.getElementById(`password-rule-${rule.key}`).dataset.met = String(satisfied);
                    document.getElementById(`password-rule-${rule.key}-marker`).textContent = satisfied ? '✓' : '○';
                    document.getElementById(`password-rule-${rule.key}-state`).textContent = satisfied ? 'Met' : 'Not met';
                }
            },
        };
    }
    return Object.freeze({ create });
})();
