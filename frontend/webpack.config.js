const path = require("path");
const HtmlWebpackPlugin = require("html-webpack-plugin");
const { merge } = require("webpack-merge");
const webpack = require("webpack");
const { CleanWebpackPlugin } = require("clean-webpack-plugin");
const MiniCssExtractPlugin = require("mini-css-extract-plugin");

const { VueLoaderPlugin } = require("vue-loader");

const common = {
  context: path.resolve(__dirname),
  entry: ["./src/index.js"],

  resolve: {
    extensions: [".js", ".vue"],
    alias: {
      vue: "@vue/compat",
    },
  },

  output: {
    path: path.resolve(__dirname, "build"),
    filename: "[name].bundle.js",
  },

  plugins: [
    new VueLoaderPlugin(),

    new HtmlWebpackPlugin({
      title: "Mozilla Code Review Bot",
      filename: "index.html",
      template: "./src/index.html",
    }),

    new webpack.ProvidePlugin({
      process: "process/browser",
    }),

    new webpack.DefinePlugin({
      // Define backend url as constant
      // using an environment variable with fallback for devs
      BACKEND_URL: JSON.stringify(
        process.env.BACKEND_URL || "http://localhost:8000"
      ),
    }),

    new MiniCssExtractPlugin({
      filename: "[name].[contenthash:8].css",
    }),
  ],

  module: {
    rules: [
      {
        test: /\.vue$/,
        loader: "vue-loader",
        options: {
          compilerOptions: {
            compatConfig: {
              MODE: 3,
              RENDER_FUNCTION: false,
            },
          },
        },
      },
      {
        test: /\.js$/,
        exclude: /node_modules/,
        use: ["babel-loader"],
      },
      {
        test: /\.(scss|css)$/,
        use: [
          MiniCssExtractPlugin.loader,
          {
            loader: "css-loader",
            options: {
              importLoaders: 0,
            },
          },
        ],
      },

      // Images: Copy image files to build folder
      { test: /\.(?:ico|gif|png|jpg|jpeg)$/i, type: "asset/resource" },

      // Fonts and SVGs: Inline files
      { test: /\.(woff(2)?|eot|ttf|otf|svg|)$/, type: "asset/inline" },
    ],
  },
};

const development = {
  mode: "development",

  devtool: "eval-cheap-module-source-map",

  devServer: {
    port: 8010,
    hot: true,
    historyApiFallback: true,
    open: true,
  },

  plugins: [
    /**
     * The compile-time flags https://vuejs.org/api/compile-time-flags need to be set
     * explicitly in vue3 (otherwise the console shows a warning)
     */
    new webpack.DefinePlugin({
      __VUE_OPTIONS_API__: "true",
      __VUE_PROD_DEVTOOLS__: "true",
      __VUE_PROD_HYDRATION_MISMATCH_DETAILS__: "true",
    }),
  ],
};

const production = {
  mode: "production",

  devtool: "source-map",

  optimization: {
    minimize: true,
    splitChunks: {
      chunks: "all",
      maxInitialRequests: 5,
      name: false,
    },
    runtimeChunk: "single",
  },

  performance: {
    hints: "error",
    maxAssetSize: 1782579.2,
    maxEntrypointSize: 2621440,
  },

  plugins: [
    new CleanWebpackPlugin({
      verbose: false,
    }),
    /**
     * The compile-time flags https://vuejs.org/api/compile-time-flags need to be set
     * explicitly in vue3 (otherwise the console shows a warning)
     */
    new webpack.DefinePlugin({
      __VUE_OPTIONS_API__: "true",
      __VUE_PROD_DEVTOOLS__: "false",
      __VUE_PROD_HYDRATION_MISMATCH_DETAILS__: "false",
    }),
  ],
};

module.exports = (env, args) => {
  switch (args.mode) {
    case "development":
      return merge(common, development);
    case "production":
      return merge(common, production);
    default:
      throw new Error("No matching configuration was found!");
  }
};
