fs = require('fs');

const envs = {
  CONFIG: process.env.CONFIG || 'staging',
};
const PORT = process.env.PORT || 8010;
// HTTPS can be disabled by setting HTTPS_DISABLED environment variable to
// true. Otherwise it will enforced either using automatically generated
// certificates or pre-generated ones.
const HTTPS = process.env.HTTPS_DISABLED ? false :
  (process.env.SSL_CERT && process.env.SSL_KEY && process.env.SSL_CACERT) ?
    {
      cert: fs.readFileSync(process.env.SSL_CERT),
      key: fs.readFileSync(process.env.SSL_KEY),
      ca: fs.readFileSync(process.env.SSL_CACERT)
    }
    : true;

// Set environment variables to their default values if not defined
Object.keys(envs).forEach(env => !(env in process.env) && (process.env[env] = envs[env]));

module.exports = {
  use: [
    '@neutrinojs/standardjs',
    [
      '@neutrinojs/vue',
      {
        html: {
          title: 'Mozilla Static Analysis'
        },
        devServer: {
          port: PORT,
          https: HTTPS,
          disableHostCheck: true,
          historyApiFallback: {
            rewrites: [
              { from: '__heartbeat__', to: 'views/ok.html' },
              { from: '__lbheartbeat__', to: 'views/ok.html' },
              { from: '__version__', to: 'views/version.json' },
            ],
          },
        }
      }
    ],
    '@neutrinojs/mocha',
    ['@neutrinojs/env', Object.keys(envs)],
  ]
};
