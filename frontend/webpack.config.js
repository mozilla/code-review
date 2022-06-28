const path = require('path');

const HtmlWebpackPlugin = require('html-webpack-plugin');

const commonConfig = {
  context: path.resolve(__dirname),
  target: 'web',
  entry: {
    index: [
      './src/index'
    ]
  },
  node: {
    Buffer: false,
    fs: 'empty',
    tls: 'empty'
  },
  output: {
    chunkFilename: '[name].[chunkhash].js',
    filename: '[name].js',
    path: path.resolve(__dirname, 'build'),
    publicPath: './'
  },
  resolve: {
    extensions: [
      '.js',
      '.jsx',
      '.vue',
      '.ts',
      '.tsx',
      '.mjs',
      '.json'
    ],
  },
  module: {
    rules: [
      {
        enforce: 'pre',
        include: [
          path.resolve(__dirname, 'src'),
        ],
        test: /\.(js|jsx|vue|ts|tsx|mjs)$/,
        use: [
          {
            loader: 'eslint-loader',
            options: {
              baseConfig: {
                'extends': [
                  'standard',
                  'standard-jsx',
                  'plugin:vue/base'
                ]
              },
              cwd: '',
              envs: [
                'es6',
                'browser',
                'commonjs'
              ],
              extensions: [
                'js',
                'jsx',
                'vue',
                'ts',
                'tsx',
                'mjs',
              ],
              failOnError: true,
              formatter: function(results) {
                  let errors = 0;
                  let warnings = 0;
                  let fixableErrors = 0;
                  let fixableWarnings = 0;

                  const resultsWithMessages = results.filter(result => result.messages.length > 0);

                  let output = resultsWithMessages.reduce((resultsOutput, result) => {
                      const messages = result.messages.map(message => `${formatMessage(message, result)}\n\n`);

                      errors += result.errorCount;
                      warnings += result.warningCount;
                      fixableErrors += result.fixableErrorCount;
                      fixableWarnings += result.fixableWarningCount;

                      return resultsOutput.concat(messages);
                  }, []).join("\n");

                  output += "\n";
                  output += formatSummary(errors, warnings, fixableErrors, fixableWarnings);

                  return (errors + warnings) > 0 ? output : "";
              },
              globals: [
                'process'
              ],
              parser: 'vue-eslint-parser',
              parserOptions: {
                ecmaFeatures: {
                  generators: true,
                  impliedStrict: true,
                  objectLiteralDuplicateProperties: false
                },
                ecmaVersion: 2017,
                parser: 'babel-eslint',
                sourceType: 'module'
              },
              plugins: [
                'babel',
                'standard',
                'vue'
              ],
              root: true,
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
              useEslintrc: false
            }
          }
        ]
      },
      {
        test: /\.(html)$/,
        use: [
          {
            loader: 'html-loader'
          }
        ]
      },
      {
        exclude: [
          path.resolve(__dirname, 'src/static'),
        ],
        include: [
          path.resolve(__dirname, 'src'),
          path.resolve(__dirname, 'test'),
        ],
        test: /\.(js|jsx|vue|ts|tsx|mjs)$/,
        use: [
          {
            loader: 'babel-loader'
          }
        ]
      },
      {
        exclude: [
          /\.(module.css)$/
        ],
        test: /\.(css)$/,
        use: [
          {
            loader: 'style-loader'
          },
          {
            loader: 'css-loader',
            options: {
              importLoaders: 0
            }
          }
        ]
      },
      {
        test: /\.(module.css)$/,
        use: [
          {
            loader: 'style-loader'
          },
          {
            loader: 'css-loader',
            options: {
              importLoaders: 0,
              modules: true
            }
          }
        ]
      },
      {
        test: /\.(woff|woff2)(\?v=\d+\.\d+\.\d+)?$/,
        use: [
          {
            loader: 'url-loader',
            options: {
              limit: 10000,
              mimetype: 'application/font-woff',
              name: '[name].[ext]'
            }
          }
        ]
      },
      {
        test: /\.ttf(\?v=\d+\.\d+\.\d+)?$/,
        use: [
          {
            loader: 'url-loader',
            options: {
              limit: 10000,
              mimetype: 'application/octet-stream',
              name: '[name].[ext]'
            }
          }
        ]
      },
      {
        test: /\.(png|jpg|jpeg|gif|webpsvg|ico)(\?v=\d+\.\d+\.\d+)?$/,
        use: [
          {
            loader: 'url-loader',
            options: {
              limit: 8192,
              name: '[name].[ext]'
            }
          }
        ]
      },
      {
        test: /\.(worker.js|worker.jsx|worker.vue|worker.ts|worker.tsx|worker.mjs)$/,
        use: [
          {
            loader: 'worker-loader'
          }
        ]
      },
      {
        test: /\.(vue)$/,
        use: [
          {
            loader: 'vue-loader',
            options: {
              extractCss: true,
              loaders: {
                js: {
                  loader: 'babel-loader',
                  options: {
                    cacheDirectory: true,
                    plugins: [
                      [
                        'fast-async',
                        {
                          spec: true
                        }
                      ],
                      'syntax-dynamic-import',
                      'transform-object-rest-spread'
                    ],
                    presets: [
                      [
                        'babel-preset-env',
                        {
                          debug: false,
                          exclude: [
                            'transform-regenerator',
                            'transform-async-to-generator'
                          ],
                          modules: false,
                          targets: {
                            browsers: [
                              'last 2 Chrome versions',
                              'last 2 Firefox versions',
                              'last 2 Edge versions',
                              'last 2 Opera versions',
                              'last 2 Safari versions',
                              'last 2 iOS versions'
                            ]
                          },
                          useBuiltIns: true
                        }
                      ]
                    ]
                  }
                }
              }
            }
          }
        ]
      }
    ]
  },
  plugins: [
    new HtmlWebpackPlugin({
      inject: false,
      template: require('html-webpack-template'),
      templateParameters: function templateParametersGenerator (compilation, assets, options) {
        return {
          compilation: compilation,
          webpack: compilation.getStats().toJson(),
          webpackConfig: compilation.options,
          htmlWebpackPlugin: {
            files: assets,
            options: options
          }
        };
      },
      filename: 'index.html',
      hash: false,
      inject: false,
      compile: true,
      favicon: false,
      minify: {
        useShortDoctype: true,
        keepClosingSlash: true,
        collapseWhitespace: true,
        preserveLineBreaks: true
      },
      cache: true,
      showErrors: true,
      chunks: [
        'index',
        'vendor',
        'runtime'
      ],
      excludeChunks: [],
      chunksSortMode: 'auto',
      meta: {},
      title: 'Mozilla Code Review Bot',
      xhtml: true,
      appMountId: 'root',
      mobile: true,
      pluginId: 'html-index'
    })
  ],
};

module.exports = (env, args) => {
  return commonConfig;
};
