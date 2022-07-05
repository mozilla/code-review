module.exports =           {
  root: true,
	extends: [
		'standard',
		'plugin:vue/base'
	],
  globals: {
    process: true,
    BACKEND_URL: true,
  },

	parser: 'vue-eslint-parser',
	parserOptions: {
		ecmaFeatures: {
			generators: true,
			impliedStrict: true,
			objectLiteralDuplicateProperties: false
		},
		ecmaVersion: 2017,
		parser: '@babel/eslint-parser',
		sourceType: 'module'
	},
	plugins: [
		'babel',
		'vue'
	],
	rules: {
		'babel/new-cap': [
			'error',
			{
				newIsCap: true
			}
		],
		'babel/object-curly-spacing': [
			'error',
			'always'
		],
		'new-cap': 'off',
		'object-curly-spacing': 'off'
	},
	settings: {},
};
