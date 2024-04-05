"""Tests for the Deep explainer."""


import numpy as np
import pandas as pd
import pytest
from packaging import version

import shap

#os.environ['CUDA_VISIBLE_DEVICES'] = '-1'

############################
# Tensorflow related tests #
############################
@pytest.mark.xfail(reason="This test is currently failing due to failed additivity of the shap values. "
                  "Seems like some of the used operations are not supported correctly.")
def test_tf_eager_rnn():
    tf = pytest.importorskip('tensorflow')

    def generate_time_series(num_data_points):
        time = np.arange(0, num_data_points)
        values = np.sin(0.1 * time) + 0.2 * np.random.randn(num_data_points)
        return values

    # Create a time series dataset
    num_data_points = 1000
    time_series = generate_time_series(num_data_points)

    # Function to create input sequences and corresponding targets
    def create_sequences(data, seq_length):
        sequences = []
        targets = []
        for i in range(len(data) - seq_length):
            seq = data[i:i+seq_length]
            target = data[i+seq_length]
            sequences.append(seq)
            targets.append(target)
        return np.array(sequences), np.array(targets)

    # Define sequence length and split data into sequences and targets
    sequence_length = 10
    X, y = create_sequences(time_series, sequence_length)

    # Reshape data for RNN input (samples, time steps, features)
    X = X.reshape((X.shape[0], X.shape[1], 1))

    # Build the RNN model using SimpleRNN layer
    model = tf.keras.models.Sequential()
    model.add(tf.keras.layers.SimpleRNN(50, input_shape=(sequence_length, 1)))
    model.add(tf.keras.layers.Dense(1))  # Output layer with one neuron for regression task

    # Compile the model
    model.compile(optimizer='adam', loss='mse')

    # Train the model
    model.fit(X, y, epochs=2, batch_size=32, validation_split=0.1)

    # Generate predictions on new data
    new_data = generate_time_series(20)
    new_sequences, _ = create_sequences(new_data, sequence_length)
    new_sequences = new_sequences.reshape((new_sequences.shape[0], new_sequences.shape[1], 1))

    # Calculate SHAP values for the data
    e = DeepExplainer(model, new_sequences)

    sv = e.shap_values(new_sequences[:10])
    model_output_values = model(new_sequences[:10])

    assert np.abs(e.expected_value[0] + sv[0].sum((1, 2)) - model_output_values[:, 0]).max() < 1e-2


def test_tf_eager_gru():
    tf = pytest.importorskip('tensorflow')
    # Generate some sample time series data
    def generate_time_series(num_data_points):
        time = np.arange(0, num_data_points)
        values = np.sin(0.1 * time) + 0.2 * np.random.randn(num_data_points)
        return values

    # Create a time series dataset
    num_data_points = 1000
    time_series = generate_time_series(num_data_points)

    # Function to create input sequences and corresponding targets
    def create_sequences(data, seq_length):
        sequences = []
        targets = []
        for i in range(len(data) - seq_length):
            seq = data[i:i+seq_length]
            target = data[i+seq_length]
            sequences.append(seq)
            targets.append(target)
        return np.array(sequences), np.array(targets)

    # Define sequence length and split data into sequences and targets
    sequence_length = 10
    X, y = create_sequences(time_series, sequence_length)

    # Reshape data for RNN input (samples, time steps, features)
    X = X.reshape((X.shape[0], X.shape[1], 1))

    # Build the RNN model using SimpleRNN layer
    model = tf.keras.models.Sequential()
    model.add(tf.keras.layers.GRU(50, input_shape=(sequence_length, 1)))
    model.add(tf.keras.layers.Dense(1))  # Output layer with one neuron for regression task

    # Compile the model
    model.compile(optimizer='adam', loss='mse')

    # Train the model
    model.fit(X, y, epochs=2, batch_size=32, validation_split=0.1)

    # Generate predictions on new data
    new_data = generate_time_series(20)
    new_sequences, _ = create_sequences(new_data, sequence_length)
    new_sequences = new_sequences.reshape((new_sequences.shape[0], new_sequences.shape[1], 1))

    e = DeepExplainer(model, new_sequences)

    sv = e.shap_values(new_sequences[:10])
    model_output_values = model(new_sequences[:10])

    assert np.abs(e.expected_value[0] + sv[0].sum((1, 2)) - model_output_values[:, 0]).max() < 1e-2


@pytest.mark.xfail(reason="This test is currently failing due to a lack of support for embeddings.")
def test_embedding():
    tf = pytest.importorskip('tensorflow')

    input1 = tf.keras.layers.Input((10,))
    emb = tf.keras.layers.Embedding(1000, 64)(input1)
    output = tf.keras.layers.Dense(1)(tf.reshape(emb, (-1, 640)))

    model = tf.keras.models.Model(input1, output)

    input_array = np.random.randint(1000, size=(1000, 10))
    model.compile('rmsprop', 'mse')

    input_array = np.random.randint(1000, size=(32, 10))

    input_array_ex = input_array.reshape((input_array.shape[0], input_array.shape[1], 1))
    explainer = DeepExplainer(model, input_array_ex[:20])

    # this fails since the embedding is not supported
    # their output always result in None if the NN is applied with overwritten gradients
    _shap_values = explainer.shap_values(input_array_ex[-20:])


@pytest.mark.xfail(reason="This test is currently failing due to failed additivity of the shap values. "
                  "Seems like some of the used operations are not supported correctly.")
def test_functional_model():
    tf = pytest.importorskip('tensorflow')

    SEQUENCE_LENGTH = 4

    # Generate some sample time series data
    def generate_time_series(num_data_points):
        time = np.random.randint(low=0, high=2, size=(num_data_points, SEQUENCE_LENGTH))
        return np.array(time, dtype=np.float32)

    # Create a time series dataset
    num_data_points = 10000
    time_series = generate_time_series(num_data_points)
    y = np.sum(time_series, axis=1)

    input1 = tf.keras.layers.Input((SEQUENCE_LENGTH, 1))
    input2 = tf.keras.layers.Input((50,))
    concat = tf.keras.layers.Concatenate(axis=1)([input1, tf.reshape(input2, shape=(-1, 50, 1))])
    batchnorm = tf.keras.layers.BatchNormalization(axis=1)(concat)
    lstm_output = tf.keras.layers.LSTM(50)(batchnorm)
    output = tf.keras.layers.Dense(1)(lstm_output)

    model = tf.keras.models.Model([input1, input2], output)

    model.compile(optimizer='adam', loss='mse')

    reshaped = time_series.reshape((time_series.shape[0], time_series.shape[1], 1))

    dummy_input2 = np.random.randn(num_data_points, 50)
    model.fit([time_series, dummy_input2], y, epochs=2, batch_size=32, validation_split=0.1)

    TEST_SAMPLES = 10
    test_series = generate_time_series(TEST_SAMPLES)

    dummy_input2 = np.random.randn(TEST_SAMPLES, 50)

    reshaped = test_series.reshape((test_series.shape[0], test_series.shape[1], 1))
    explainer = DeepExplainer(model, [reshaped, dummy_input2])

    # todo: check additivity is false here, so investigate what is going wrong!
    _shap_values = explainer.shap_values([reshaped, dummy_input2])


def test_tf_eager_lstm():
    # This test should pass with tf 2.x
    tf = pytest.importorskip('tensorflow')
    # split a univariate sequence into samples
    def split_sequence(sequence, n_steps):
        X, y = list(), list()
        for i in range(len(sequence)):
            # find the end of this pattern
            end_ix = i + n_steps
            # check if we are beyond the sequence
            if end_ix > len(sequence)-1:
                break
            # gather input and output parts of the pattern
            seq_x, seq_y = sequence[i:end_ix], sequence[end_ix]
            X.append(seq_x)
            y.append(seq_y)
            return np.array(X), np.array(y)

    # define input sequence
    raw_seq = [10, 20, 30, 40, 50, 60, 70, 80, 90]
    # choose a number of time steps
    n_steps = 3
    # split into samples
    X, y = split_sequence(raw_seq, n_steps)
    # reshape from [samples, timesteps] into [samples, timesteps, features]
    n_features = 1
    X = X.reshape((X.shape[0], X.shape[1], n_features))
    # define model
    model = tf.keras.models.Sequential()
    model.add(tf.keras.layers.LSTM(50, activation='relu', input_shape=(n_steps, n_features)))
    model.add(tf.keras.layers.Dense(1))
    model.compile(optimizer='adam', loss='mse')
    # fit model
    model.fit(X, y, epochs=200, verbose=0)
    # demonstrate prediction
    x_input = np.array([70, 80, 90], dtype=np.float32)
    x_input = x_input.reshape((1, n_steps, n_features))

    e = DeepExplainer(model, x_input)
    sv = e.shap_values(x_input)

    assert np.abs(e.expected_value[0] + sv[0].sum(-1) - model(x_input)[:, 0]).max() < 1e-4

def test_tf_eager_stacked_lstms():
    # this test should pass with tf 2.x
    tf = pytest.importorskip('tensorflow')

    # Define the start and end datetime
    start_datetime = pd.to_datetime('2020-01-01 00:00:00')
    end_datetime = pd.to_datetime('2023-03-31 23:00:00')

    # Generate a DatetimeIndex with hourly frequency
    date_rng = pd.date_range(start=start_datetime, end=end_datetime, freq='H')

    # Create a DataFrame with random data for 7 features
    num_samples = len(date_rng)
    num_features = 7

    # Generate random data for the DataFrame
    data = np.random.rand(num_samples, num_features)

    # Create the DataFrame with a DatetimeIndex
    df = pd.DataFrame(data, index=date_rng, columns=[f'X{i}' for i in range(1, num_features+1)])


    def windowed_dataset(series=None, in_horizon=None, out_horizon=None, delay=None, batch_size=None):
        '''
        Convert multivariate data into input and output sequences.
        Convert NumPy arrays to TensorFlow tensors.
        Arguments:
        ===========
        series: a list or array of time-series data.
        total_horizon: an integer representing the size of the input window.
        out_horizon: an integer representing the size of the output window.
        delay: an integer representing the number of steps between each input window.
        batch_size: an integer representing the batch size.
        '''
        total_horizon = in_horizon + out_horizon
        dataset = tf.data.Dataset.from_tensor_slices(series)
        dataset = dataset.window(total_horizon, shift=delay, drop_remainder=True)
        dataset = dataset.flat_map(lambda window: window.batch(total_horizon))
        dataset = dataset.map(lambda window: (window[:-out_horizon,:], window[-out_horizon:,0]))
        dataset = dataset.batch(batch_size).prefetch(1)
        return dataset

    # Define the proportions for the splits (70:20:10)%
    train_size = 0.4
    valid_size = 0.5

    # Calculate the split points
    train_split = int(len(df)*train_size)
    valid_split = int(len(df)*(train_size + valid_size))

    # Split the DataFrame
    df_train = df.iloc[:train_split]
    df_valid = df.iloc[train_split:valid_split]
    df_test = df.iloc[valid_split:]

    # number of input features and output targets
    n_features = df.shape[1]

    # split the data into sliding sequential windows
    train_dataset = windowed_dataset(series=df_train.values,
                                    in_horizon=100,
                                    out_horizon=3,
                                    delay=1,
                                    batch_size=32)

    windowed_dataset(series=df_valid.values,
                                    in_horizon=100,
                                    out_horizon=3,
                                    delay=1,
                                    batch_size=32)

    windowed_dataset(series=df_test.values,
                                in_horizon=100,
                                out_horizon=3,
                                delay=1,
                                batch_size=32)

    input_layer = tf.keras.layers.Input(shape=(100, n_features))
    lstm_layer1 = tf.keras.layers.LSTM(5, return_sequences=True)(input_layer)
    lstm_layer2 = tf.keras.layers.LSTM(5, return_sequences=True)(lstm_layer1)
    lstm_layer3 = tf.keras.layers.LSTM(5)(lstm_layer2)
    output_layer = tf.keras.layers.Dense(3)(lstm_layer3)
    model = tf.keras.models.Model(inputs=input_layer, outputs=output_layer)

    model.compile(optimizer=tf.keras.optimizers.Adam(learning_rate=0.01), loss='mse', metrics=['mae'])

    def tensor_to_arrays(input_obj=None):
        '''
        Convert a "tensorflow.python.data.ops.dataset_ops.PrefetchDataset" object into a numpy arrays.
        This function can be used to slice the tensor objects out of the `windowing` function.
        '''
        x = list(map(lambda x: x[0], input_obj))
        y = list(map(lambda x: x[1], input_obj))

        x_ = [xtmp.numpy() for xtmp in x]
        y_ = [ytmp.numpy() for ytmp in y]

        # Stack the arrays vertically
        x = np.vstack(x_)
        y = np.vstack(y_)

        return x, y


    xarr, yarr = tensor_to_arrays(input_obj=train_dataset)

    # Create an explainer object
    e = shap.DeepExplainer(model, xarr[:100, :, :])

    # Calculate SHAP values for the data
    sv = e.shap_values(xarr[:100, :, :], check_additivity=False)
    model_output_values = model(xarr[:100, :, :])

    # todo: this might indicate an error in how the gradients are overwritten
    for dim in range(3):
        assert (model_output_values[:, dim].numpy() - e.expected_value[dim].numpy() - sv[dim].sum(axis=tuple(range(1, sv[dim].ndim)))).max() < 0.02


def test_tf_eager_call(random_seed):
    """This is a basic eager example from keras."""
    tf = pytest.importorskip('tensorflow')

    tf.compat.v1.random.set_random_seed(random_seed)
    rs = np.random.RandomState(random_seed)

    if version.parse(tf.__version__) >= version.parse("2.4.0"):
        pytest.skip("Deep explainer does not work for TF 2.4 in eager mode.")

    x = pd.DataFrame({"B": rs.random(size=(100,))})
    y = x.B
    y = y.map(lambda zz: chr(int(zz * 2 + 65))).str.get_dummies()

    model = tf.keras.models.Sequential()
    model.add(tf.keras.layers.Dense(10, input_shape=(x.shape[1],), activation="relu"))
    model.add(tf.keras.layers.Dense(y.shape[1], input_shape=(10,), activation="softmax"))
    model.summary()
    model.compile(loss="categorical_crossentropy", optimizer="Adam")
    model.fit(x.values, y.values, epochs=2)

    e = shap.DeepExplainer(model, x.values[:1])
    sv = e.shap_values(x.values)
    sv_call = e(x.values)
    np.testing.assert_array_almost_equal(sv, sv_call.values, decimal=8)
    assert np.abs(e.expected_value[0] + sv[0].sum(-1) - model(x.values)[:, 0]).max() < 1e-4


def test_tf_keras_mnist_cnn_call(random_seed):
    """This is the basic mnist cnn example from keras."""
    tf = pytest.importorskip('tensorflow')
    rs = np.random.RandomState(random_seed)
    tf.compat.v1.random.set_random_seed(random_seed)

    from tensorflow import keras
    from tensorflow.compat.v1 import ConfigProto, InteractiveSession
    from tensorflow.keras import backend as K
    from tensorflow.keras.layers import (
        Activation,
        Conv2D,
        Dense,
        Dropout,
        Flatten,
        MaxPooling2D,
    )
    from tensorflow.keras.models import Sequential

    config = ConfigProto()
    config.gpu_options.allow_growth = True
    sess = InteractiveSession(config=config)

    tf.compat.v1.disable_eager_execution()

    batch_size = 64
    num_classes = 10
    epochs = 1

    # input image dimensions
    img_rows, img_cols = 28, 28

    # the data, split between train and test sets
    # (x_train, y_train), (x_test, y_test) = keras.datasets.mnist.load_data()
    x_train = rs.randn(200, 28, 28)
    y_train = rs.randint(0, 9, 200)
    x_test = rs.randn(200, 28, 28)
    y_test = rs.randint(0, 9, 200)

    if K.image_data_format() == 'channels_first':
        x_train = x_train.reshape(x_train.shape[0], 1, img_rows, img_cols)
        x_test = x_test.reshape(x_test.shape[0], 1, img_rows, img_cols)
        input_shape = (1, img_rows, img_cols)
    else:
        x_train = x_train.reshape(x_train.shape[0], img_rows, img_cols, 1)
        x_test = x_test.reshape(x_test.shape[0], img_rows, img_cols, 1)
        input_shape = (img_rows, img_cols, 1)

    x_train = x_train.astype('float32')
    x_test = x_test.astype('float32')
    x_train /= 255
    x_test /= 255

    # convert class vectors to binary class matrices
    y_train = keras.utils.to_categorical(y_train, num_classes)
    y_test = keras.utils.to_categorical(y_test, num_classes)

    model = Sequential()
    model.add(Conv2D(2, kernel_size=(3, 3),
                     activation='relu',
                     input_shape=input_shape))
    model.add(Conv2D(4, (3, 3), activation='relu'))
    model.add(MaxPooling2D(pool_size=(2, 2)))
    model.add(Dropout(0.25))
    model.add(Flatten())
    model.add(Dense(16, activation='relu')) # 128
    model.add(Dropout(0.5))
    model.add(Dense(num_classes))
    model.add(Activation('softmax'))

    model.compile(loss=keras.losses.categorical_crossentropy,
                  optimizer=keras.optimizers.legacy.Adadelta(),
                  metrics=['accuracy'])

    model.fit(x_train[:10, :], y_train[:10, :],
              batch_size=batch_size,
              epochs=epochs,
              verbose=1,
              validation_data=(x_test[:10, :], y_test[:10, :]))

    # explain by passing the tensorflow inputs and outputs
    inds = rs.choice(x_train.shape[0], 3, replace=False)
    e = shap.DeepExplainer((model.layers[0].input, model.layers[-1].input), x_train[inds, :, :])
    shap_values = e.shap_values(x_test[:1])
    shap_values_call = e(x_test[:1])

    np.testing.assert_array_almost_equal(shap_values, shap_values_call.values, decimal=8)

    predicted = sess.run(model.layers[-1].input, feed_dict={model.layers[0].input: x_test[:1]})

    sums = shap_values.sum(axis=(1, 2, 3))
    np.testing.assert_allclose(sums + e.expected_value, predicted, atol=1e-3), "Sum of SHAP values does not match difference!"
    sess.close()

@pytest.mark.parametrize("activation", ["relu", "elu", "selu"])
def test_tf_keras_activations(activation):
    """Test verifying that a linear model with linear data gives the correct result."""
    # FIXME: this test should ideally pass with any random seed. See #2960
    random_seed = 0

    tf = pytest.importorskip('tensorflow')

    from tensorflow.keras.layers import Dense, Input
    from tensorflow.keras.models import Model
    from tensorflow.keras.optimizers.legacy import SGD

    tf.compat.v1.disable_eager_execution()

    tf.compat.v1.random.set_random_seed(random_seed)
    rs = np.random.RandomState(random_seed)

    # coefficients relating y with x1 and x2.
    coef = np.array([1, 2]).T

    # generate data following a linear relationship
    x = rs.normal(1, 10, size=(1000, len(coef)))
    y = np.dot(x, coef) + 1 + rs.normal(scale=0.1, size=1000)

    # create a linear model
    inputs = Input(shape=(2,))
    preds = Dense(1, activation=activation)(inputs)

    model = Model(inputs=inputs, outputs=preds)
    model.compile(optimizer=SGD(), loss='mse', metrics=['mse'])
    model.fit(x, y, epochs=30, shuffle=False, verbose=0)

    # explain
    e = shap.DeepExplainer((model.layers[0].input, model.layers[-1].output), x)
    shap_values = e.shap_values(x)
    preds = model.predict(x)

    assert shap_values.shape == (1000, 2, 1)
    np.testing.assert_allclose(shap_values.sum(axis=1) + e.expected_value, preds, atol=1e-5)


def test_tf_keras_linear():
    """Test verifying that a linear model with linear data gives the correct result."""
    # FIXME: this test should ideally pass with any random seed. See #2960
    random_seed = 0

    tf = pytest.importorskip('tensorflow')

    from tensorflow.keras.layers import Dense, Input
    from tensorflow.keras.models import Model
    from tensorflow.keras.optimizers.legacy import SGD

    tf.compat.v1.disable_eager_execution()

    tf.compat.v1.random.set_random_seed(random_seed)
    rs = np.random.RandomState(random_seed)

    # coefficients relating y with x1 and x2.
    coef = np.array([1, 2]).T

    # generate data following a linear relationship
    x = rs.normal(1, 10, size=(1000, len(coef)))
    y = np.dot(x, coef) + 1 + rs.normal(scale=0.1, size=1000)

    # create a linear model
    inputs = Input(shape=(2,))
    preds = Dense(1, activation='linear')(inputs)

    model = Model(inputs=inputs, outputs=preds)
    model.compile(optimizer=SGD(), loss='mse', metrics=['mse'])
    model.fit(x, y, epochs=30, shuffle=False, verbose=0)

    fit_coef = model.layers[1].get_weights()[0].T[0]

    # explain
    e = shap.DeepExplainer((model.layers[0].input, model.layers[-1].output), x)
    shap_values = e.shap_values(x)

    assert shap_values.shape == (1000, 2, 1)

    # verify that the explanation follows the equation in LinearExplainer
    expected = (x - x.mean(0)) * fit_coef
    np.testing.assert_allclose(shap_values.sum(-1), expected, atol=1e-5)


def test_tf_keras_imdb_lstm(random_seed):
    """Basic LSTM example using the keras API defined in tensorflow"""
    tf = pytest.importorskip('tensorflow')
    rs = np.random.RandomState(random_seed)
    tf.compat.v1.random.set_random_seed(random_seed)

    # this fails right now for new TF versions (there is a warning in the code for this)
    if version.parse(tf.__version__) >= version.parse("2.5.0"):
        pytest.skip()

    from tensorflow.keras.datasets import imdb
    from tensorflow.keras.layers import LSTM, Dense, Embedding
    from tensorflow.keras.models import Sequential
    from tensorflow.keras.preprocessing import sequence

    tf.compat.v1.disable_eager_execution()

    # load the data from keras
    max_features = 1000
    try:
        (X_train, _), (X_test, _) = imdb.load_data(num_words=max_features)
    except Exception:
        return # this hides a bug in the most recent version of keras that prevents data loading
    X_train = sequence.pad_sequences(X_train, maxlen=100)
    X_test = sequence.pad_sequences(X_test, maxlen=100)

    # create the model. note that this is model is very small to make the test
    # run quick and we don't care about accuracy here
    mod = Sequential()
    mod.add(Embedding(max_features, 8))
    mod.add(LSTM(10, dropout=0.2, recurrent_dropout=0.2))
    mod.add(Dense(1, activation='sigmoid'))
    mod.compile(loss='binary_crossentropy', optimizer='adam', metrics=['accuracy'])

    # select the background and test samples
    inds = rs.choice(X_train.shape[0], 3, replace=False)
    background = X_train[inds]
    testx = X_test[10:11]

    # explain a prediction and make sure it sums to the difference between the average output
    # over the background samples and the current output
    sess = tf.compat.v1.keras.backend.get_session()
    sess.run(tf.compat.v1.global_variables_initializer())
    # For debugging, can view graph:
    # writer = tf.compat.v1.summary.FileWriter("c:\\tmp", sess.graph)
    # writer.close()
    e = shap.DeepExplainer((mod.layers[0].input, mod.layers[-1].output), background)
    shap_values = e.shap_values(testx)
    sums = np.array([shap_values[i].sum() for i in range(len(shap_values))])
    diff = sess.run(mod.layers[-1].output, feed_dict={mod.layers[0].input: testx})[0, :] - \
        sess.run(mod.layers[-1].output, feed_dict={mod.layers[0].input: background}).mean(0)
    np.testing.testing_allclose(sums, diff, atol=1e-02), "Sum of SHAP values does not match difference!"


def test_tf_deep_imbdb_transformers():
    # GH 3522
    transformers = pytest.importorskip('transformers')

    from shap import models

    # data from datasets imdb dataset
    short_data = ['I lov', 'Worth', 'its a', 'STAR ', 'First', 'I had', 'Isaac', 'It ac', 'Techn', 'Hones']
    classifier = transformers.pipeline("sentiment-analysis", return_all_scores=True)
    pmodel = models.TransformersPipeline(classifier, rescale_to_logits=True)
    explainer3 = shap.Explainer(pmodel, classifier.tokenizer)
    shap_values3 = explainer3(short_data[:10])
    shap.plots.text(shap_values3[:, :, 1])
    shap.plots.bar(shap_values3[:, :, 1].mean(0))


def test_tf_deep_multi_inputs_multi_outputs():
    tf = pytest.importorskip('tensorflow')

    input1 = tf.keras.layers.Input(shape=(3,))
    input2 = tf.keras.layers.Input(shape=(4,))

    # Concatenate input layers
    concatenated = tf.keras.layers.concatenate([input1, input2])

    # Dense layers
    x = tf.keras.layers.Dense(16, activation='relu')(concatenated)

    # Output layer
    output = tf.keras.layers.Dense(3, activation='softmax')(x)
    model = tf.keras.models.Model(inputs=[input1, input2], outputs=output)
    batch_size = 32
    # Generate random input data for input1 with shape (batch_size, 3)
    input1_data = np.random.rand(batch_size, 3)

    # Generate random input data for input2 with shape (batch_size, 4)
    input2_data = np.random.rand(batch_size, 4)

    predicted = model.predict([input1_data, input2_data])
    explainer = shap.DeepExplainer(model, [input1_data, input2_data])
    shap_values = explainer.shap_values([input1_data, input2_data])
    np.testing.assert_allclose(shap_values[0].sum(1) + shap_values[1].sum(1) + explainer.expected_value, predicted, atol=1e-3)

#######################
# Torch related tests #
#######################

def _torch_cuda_available():
    """Checks whether cuda is available. If so, torch-related tests are also tested on gpu."""
    try:
        import torch

        return torch.cuda.is_available()
    except ImportError:
        pass

    return False


TORCH_DEVICES = [
                    "cpu",
                    pytest.param(
                        "cuda",
                        marks=pytest.mark.skipif(not _torch_cuda_available(), reason="cuda unavailable (with torch)")
                    ),
]


@pytest.mark.parametrize("torch_device", TORCH_DEVICES)
@pytest.mark.parametrize("interim", [True, False])
def test_pytorch_mnist_cnn_call(torch_device, interim):
    """The same test as above, but for pytorch"""
    torch = pytest.importorskip('torch')

    from torch import nn
    from torch.nn import functional as F

    class RandData:
        """Random test data."""

        def __init__(self, batch_size):
            self.current = 0
            self.batch_size = batch_size

        def __iter__(self):
            return self

        def __next__(self):
            self.current += 1
            if self.current < 10:
                return torch.randn(self.batch_size, 1, 28, 28), torch.randint(0, 9, (self.batch_size,))
            raise StopIteration


    class Net(nn.Module):
        """Basic conv net."""

        def __init__(self):
            super().__init__()
            # Testing several different activations
            self.conv_layers = nn.Sequential(
                nn.Conv2d(1, 10, kernel_size=5),
                nn.MaxPool2d(2),
                nn.Tanh(),
                nn.Conv2d(10, 20, kernel_size=5),
                nn.ConvTranspose2d(20, 20, 1),
                nn.AdaptiveAvgPool2d(output_size=(4, 4)),
                nn.Softplus(),
            )
            self.fc_layers = nn.Sequential(
                nn.Linear(320, 50),
                nn.BatchNorm1d(50),
                nn.ReLU(),
                nn.Linear(50, 10),
                nn.ELU(),
                nn.Softmax(dim=1)
            )

        def forward(self, x):
            """Run the model."""
            x = self.conv_layers(x)
            x = x.view(-1, 320)
            x = self.fc_layers(x)
            return x


    def train(model, device, train_loader, optimizer, _, cutoff=20):
        model.train()
        num_examples = 0
        for _, (data, target) in enumerate(train_loader):
            num_examples += target.shape[0]
            data, target = data.to(device), target.to(device)
            optimizer.zero_grad()
            output = model(data)
            loss = F.mse_loss(output, torch.eye(10).to(device)[target])

            loss.backward()
            optimizer.step()

            if num_examples > cutoff:
                break


    # FIXME: this test should ideally pass with any random seed. See #2960
    random_seed = 42

    torch.manual_seed(random_seed)
    rs = np.random.RandomState(random_seed)

    batch_size = 32

    train_loader = RandData(batch_size)
    test_loader = RandData(batch_size)

    model = Net()
    optimizer = torch.optim.SGD(model.parameters(), lr=0.01, momentum=0.5)

    device = torch.device(torch_device)

    model.to(device)
    train(model, device, train_loader, optimizer, 1)

    next_x, _ = next(iter(train_loader))
    inds = rs.choice(next_x.shape[0], 3, replace=False)

    next_x_random_choices = next_x[inds, :, :, :].to(device)

    if interim:
        e = shap.DeepExplainer((model, model.conv_layers[0]), next_x_random_choices)
    else:
        e = shap.DeepExplainer(model, next_x_random_choices)

    test_x, _ = next(iter(test_loader))
    input_tensor = test_x[:1].to(device)
    shap_values = e.shap_values(input_tensor)
    shap_values_call = e(input_tensor)

    np.testing.assert_array_almost_equal(shap_values, shap_values_call.values, decimal=8)

    model.eval()
    model.zero_grad()

    with torch.no_grad():
        outputs = model(input_tensor).detach().cpu().numpy()

    sums = shap_values.sum((1, 2, 3))
    np.testing.assert_allclose(sums + e.expected_value, outputs, atol=1e-3), "Sum of SHAP values does not match difference!"


@pytest.mark.parametrize("torch_device", TORCH_DEVICES)
def test_pytorch_custom_nested_models(torch_device):
    """Testing single outputs"""
    torch = pytest.importorskip('torch')

    from sklearn.datasets import fetch_california_housing
    from torch import nn
    from torch.nn import functional as F
    from torch.utils.data import DataLoader, TensorDataset

    class CustomNet1(nn.Module):
        """Model 1."""

        def __init__(self, num_features):
            super().__init__()
            self.net = nn.Sequential(
                nn.Sequential(
                    nn.Conv1d(1, 1, 1),
                    nn.ConvTranspose1d(1, 1, 1),
                ),
                nn.AdaptiveAvgPool1d(output_size=num_features // 2),
            )

        def forward(self, X):
            """Run the model."""
            return self.net(X.unsqueeze(1)).squeeze(1)

    class CustomNet2(nn.Module):
        """Model 2."""

        def __init__(self, num_features):
            super().__init__()
            self.net = nn.Sequential(
                nn.LeakyReLU(),
                nn.Linear(num_features // 2, 2)
            )

        def forward(self, X):
            """Run the model."""
            return self.net(X).unsqueeze(1)

    class CustomNet(nn.Module):
        """Model 3."""

        def __init__(self, num_features):
            super().__init__()
            self.net1 = CustomNet1(num_features)
            self.net2 = CustomNet2(num_features)
            self.maxpool2 = nn.MaxPool1d(kernel_size=2)

        def forward(self, X):
            """Run the model."""
            x = self.net1(X)
            return self.maxpool2(self.net2(x)).squeeze(1)


    def train(model, device, train_loader, optimizer, epoch):
        model.train()
        num_examples = 0
        for batch_idx, (data, target) in enumerate(train_loader):
            num_examples += target.shape[0]
            data, target = data.to(device), target.to(device)
            optimizer.zero_grad()
            output = model(data)
            loss = F.mse_loss(output.squeeze(1), target)
            loss.backward()
            optimizer.step()
            if batch_idx % 2 == 0:
                print(
                    f"Train Epoch: {epoch} [{batch_idx * len(data)}/{len(train_loader.dataset)}"
                    f" ({100. * batch_idx / len(train_loader):.0f}%)]"
                    f"\tLoss: {loss.item():.6f}"
                )


    random_seed = 777  # TODO: #2960

    torch.manual_seed(random_seed)
    rs = np.random.RandomState(random_seed)

    X, y = fetch_california_housing(return_X_y=True)

    num_features = X.shape[1]

    data = TensorDataset(
                torch.tensor(X).float(),
                torch.tensor(y).float(),
    )

    loader = DataLoader(data, batch_size=128)

    model = CustomNet(num_features)
    optimizer = torch.optim.Adam(model.parameters())

    device = torch.device(torch_device)

    model.to(device)

    train(model, device, loader, optimizer, 1)

    next_x, _ = next(iter(loader))

    inds = rs.choice(next_x.shape[0], 20, replace=False)

    next_x_random_choices = next_x[inds, :].to(device)
    e = shap.DeepExplainer(model, next_x_random_choices)

    test_x_tmp, _ = next(iter(loader))
    test_x = test_x_tmp[:1].to(device)

    shap_values = e.shap_values(test_x)

    model.eval()
    model.zero_grad()

    with torch.no_grad():
        diff = model(test_x).detach().cpu().numpy()

    sums = shap_values.sum(axis=(1))
    np.testing.assert_allclose(sums + e.expected_value, diff, atol=1e-3), "Sum of SHAP values does not match difference!"


@pytest.mark.parametrize("torch_device", TORCH_DEVICES)
def test_pytorch_single_output(torch_device):
    """Testing single outputs"""
    torch = pytest.importorskip('torch')

    from sklearn.datasets import fetch_california_housing
    from torch import nn
    from torch.nn import functional as F
    from torch.utils.data import DataLoader, TensorDataset

    class Net(nn.Module):
        """Test model."""

        def __init__(self, num_features):
            super().__init__()
            self.linear = nn.Linear(num_features // 2, 2)
            self.conv1d = nn.Conv1d(1, 1, 1)
            self.convt1d = nn.ConvTranspose1d(1, 1, 1)
            self.leaky_relu = nn.LeakyReLU()
            self.aapool1d = nn.AdaptiveAvgPool1d(output_size=num_features // 2)
            self.maxpool2 = nn.MaxPool1d(kernel_size=2)

        def forward(self, X):
            """Run the model."""
            x = self.aapool1d(self.convt1d(self.conv1d(X.unsqueeze(1)))).squeeze(1)
            return self.maxpool2(self.linear(self.leaky_relu(x)).unsqueeze(1)).squeeze(1)


    def train(model, device, train_loader, optimizer, epoch):
        model.train()
        num_examples = 0
        for batch_idx, (data, target) in enumerate(train_loader):
            num_examples += target.shape[0]
            data, target = data.to(device), target.to(device)
            optimizer.zero_grad()
            output = model(data)
            loss = F.mse_loss(output.squeeze(1), target)
            loss.backward()
            optimizer.step()
            if batch_idx % 2 == 0:
                print(
                    f"Train Epoch: {epoch} [{batch_idx * len(data)}/{len(train_loader.dataset)}"
                    f" ({100. * batch_idx / len(train_loader):.0f}%)]"
                    f"\tLoss: {loss.item():.6f}"
                )


    # FIXME: this test should ideally pass with any random seed. See #2960
    random_seed = 0
    torch.manual_seed(random_seed)
    rs = np.random.RandomState(random_seed)

    X, y = fetch_california_housing(return_X_y=True)

    num_features = X.shape[1]

    data = TensorDataset(
                torch.tensor(X).float(),
                torch.tensor(y).float(),
    )

    loader = DataLoader(data, batch_size=128)

    model = Net(num_features)
    optimizer = torch.optim.Adam(model.parameters())

    device = torch.device(torch_device)

    model.to(device)

    train(model, device, loader, optimizer, 1)

    next_x, _ = next(iter(loader))
    inds = rs.choice(next_x.shape[0], 20, replace=False)

    next_x_random_choices = next_x[inds, :].to(device)

    e = shap.DeepExplainer(model, next_x_random_choices)
    test_x_tmp, _ = next(iter(loader))
    test_x = test_x_tmp[:1].to(device)

    shap_values = e.shap_values(test_x)

    model.eval()
    model.zero_grad()

    with torch.no_grad():
        outputs = model(test_x).detach().cpu().numpy()

    sums = shap_values.sum(axis=(1))
    np.testing.assert_allclose(sums + e.expected_value, outputs, atol=1e-3), "Sum of SHAP values does not match difference!"


@pytest.mark.parametrize("torch_device", TORCH_DEVICES)
@pytest.mark.parametrize("disconnected", [True, False])
def test_pytorch_multiple_inputs(torch_device, disconnected):
    """Check a multi-input scenario."""
    torch = pytest.importorskip('torch')

    from sklearn.datasets import fetch_california_housing
    from torch import nn
    from torch.nn import functional as F
    from torch.utils.data import DataLoader, TensorDataset


    class Net(nn.Module):
        """Testing model."""

        def __init__(self, num_features, disconnected):
            super().__init__()
            self.disconnected = disconnected
            if disconnected:
                num_features = num_features // 2
            self.linear = nn.Linear(num_features, 2)
            self.output = nn.Sequential(
                nn.MaxPool1d(2),
                nn.ReLU()
            )

        def forward(self, x1, x2):
            """Run the model."""
            if self.disconnected:
                x = self.linear(x1).unsqueeze(1)
            else:
                x = self.linear(torch.cat((x1, x2), dim=-1)).unsqueeze(1)
            return self.output(x).squeeze(1)


    def train(model, device, train_loader, optimizer, epoch):
        model.train()
        num_examples = 0
        for batch_idx, (data1, data2, target) in enumerate(train_loader):
            num_examples += target.shape[0]
            data1, data2, target = data1.to(device), data2.to(device), target.to(device)
            optimizer.zero_grad()
            output = model(data1, data2)
            loss = F.mse_loss(output.squeeze(1), target)
            loss.backward()
            optimizer.step()
            if batch_idx % 2 == 0:
                print(
                    f"Train Epoch: {epoch} [{batch_idx * len(data)}/{len(train_loader.dataset)}"
                    f" ({100. * batch_idx / len(train_loader):.0f}%)]"
                    f"\tLoss: {loss.item():.6f}"
                )

    random_seed = 42  # TODO: 2960
    torch.manual_seed(random_seed)
    rs = np.random.RandomState(random_seed)

    X, y = fetch_california_housing(return_X_y=True)

    num_features = X.shape[1]
    x1 = X[:, num_features // 2:]
    x2 = X[:, :num_features // 2]

    data = TensorDataset(
                torch.tensor(x1).float(),
                torch.tensor(x2).float(),
                torch.tensor(y).float(),
    )

    loader = DataLoader(data, batch_size=128)

    model = Net(num_features, disconnected)
    optimizer = torch.optim.Adam(model.parameters())

    device = torch.device(torch_device)

    model.to(device)

    train(model, device, loader, optimizer, 1)

    next_x1, next_x2, _ = next(iter(loader))
    inds = rs.choice(next_x1.shape[0], 20, replace=False)
    background = [next_x1[inds, :].to(device), next_x2[inds, :].to(device)]
    e = shap.DeepExplainer(model, background)

    test_x1_tmp, test_x2_tmp, _ = next(iter(loader))
    test_x1 = test_x1_tmp[:1].to(device)
    test_x2 = test_x2_tmp[:1].to(device)

    shap_values = e.shap_values([test_x1[:1], test_x2[:1]])

    model.eval()
    model.zero_grad()

    with torch.no_grad():
        outputs = model(test_x1, test_x2[:1]).detach().cpu().numpy()

    # the shap values have the shape (num_samples, num_features, num_inputs, num_outputs)
    # so since we have just one output, we slice it out
    sums = shap_values[0].sum(1) + shap_values[1].sum(1)
    np.testing.assert_allclose(sums + e.expected_value, outputs, atol=1e-3), "Sum of SHAP values does not match difference!"
