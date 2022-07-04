const path = require('path');
const HtmlWebpackPlugin = require('html-webpack-plugin');
const { merge } = require('webpack-merge');
const webpack = require('webpack');

/*
const { CleanWebpackPlugin } = require('clean-webpack-plugin')
const CopyWebpackPlugin = require('copy-webpack-plugin')
const HtmlWebpackPlugin = require('html-webpack-plugin')
*/

const { VueLoaderPlugin } = require('vue-loader')

const common = {
  context: path.resolve(__dirname),
  entry: [ './src/index.js'],

  resolve: {
		extensions: [ '.js', '.vue' ],
  },

  // Where webpack outputs the assets and bundles
  output: {
    path: path.resolve(__dirname, 'build'),
    filename: '[name].bundle.js',
    publicPath: '/',
  },

  // Customize the webpack build process
  plugins: [

    new VueLoaderPlugin(),

    // Removes/cleans build folders and unused assets when rebuilding
    //new CleanWebpackPlugin(),

    // Copies files from target to destination folder
		/*
    new CopyWebpackPlugin({
      patterns: [
        {
          from: paths.public,
          to: 'assets',
          globOptions: {
            ignore: ['*.DS_Store'],
          },
        },
      ],
    }),
		*/

    // Generates an HTML file from a template
    // Generates deprecation warning: https://github.com/jantimon/html-webpack-plugin/issues/1501
    new HtmlWebpackPlugin({
      title: 'Code Review Bot',
      filename: 'index.html',
    }),

    new webpack.ProvidePlugin({
      process: 'process/browser',
    }),
  ],

  // Determine how modules within the project are treated
  module: {
    rules: [
      // JavaScript: Use Babel to transpile JavaScript files
	  {test: /\.vue$/, loader: 'vue-loader'


		},
      {test: /\.js$/, exclude: /node_modules/, use: ['babel-loader']},

      // Styles: Inject CSS into the head with source maps
      {
        test: /\.(scss|css)$/,
        use: [
		  'style-loader',
          {loader: 'css-loader', options: {sourceMap: true, importLoaders: 1}},
        ],
      },

      // Images: Copy image files to build folder
      {test: /\.(?:ico|gif|png|jpg|jpeg)$/i, type: 'asset/resource'},

      // Fonts and SVGs: Inline files
      {test: /\.(woff(2)?|eot|ttf|otf|svg|)$/, type: 'asset/inline'},
    ],
  },
};

const development = {
	mode: 'development',

  devtool: 'eval-cheap-module-source-map',

	// Enable local web server
  devServer: {
    port: 8000,
    hot: true,
    historyApiFallback: true,
    open: true,
	}
};

const production = {
	mode: 'production',
};

module.exports = (env, args) => {
  switch (args.mode) {
    case 'development':
      return merge(common, development);
    case 'production':
      return merge(common, production);
    default:
      throw new Error('No matching configuration was found!');
  }
};
