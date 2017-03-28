from __future__ import absolute_import
import numpy as np
import six
from . import backend as K
from .utils.generic_utils import serialize_keras_object
from .utils.generic_utils import deserialize_keras_object


class Initializer(object):
    """Initializer base class: all initializers inherit from this class.
    """

    def __call__(self, shape, dtype=None):
        raise NotImplementedError

    def get_config(self):
        return {}

    @classmethod
    def from_config(cls, config):
        return cls(**config)


class Zeros(Initializer):
    """Initializer that generates tensors initialized to 0."""

    def __call__(self, shape, dtype=None):
        return K.constant(0, shape=shape, dtype=dtype)


class Ones(Initializer):
    """Initializer that generates tensors initialized to 1."""

    def __call__(self, shape, dtype=None):
        return K.constant(1, shape=shape, dtype=dtype)


class Constant(Initializer):
    """Initializer that generates tensors initialized to a constant value.

    # Arguments
        value: float; the value of the generator tensors.
    """

    def __init__(self, value=0):
        self.value = value

    def __call__(self, shape, dtype=None):
        return K.constant(self.value, shape=shape, dtype=dtype)

    def get_config(self):
        return {'value': self.value}


class RandomNormal(Initializer):
    """Initializer that generates tensors with a normal distribution.

    # Arguments
        mean: a python scalar or a scalar tensor. Mean of the random values
          to generate.
        stddev: a python scalar or a scalar tensor. Standard deviation of the
          random values to generate.
        seed: A Python integer. Used to seed the random generator.
    """

    def __init__(self, mean=0., stddev=0.05, seed=None):
        self.mean = mean
        self.stddev = stddev
        self.seed = seed

    def __call__(self, shape, dtype=None):
        return K.random_normal(shape, self.mean, self.stddev,
                               dtype=dtype, seed=self.seed)

    def get_config(self):
        return {
            'mean': self.mean,
            'stddev': self.stddev,
            'seed': self.seed
        }


class RandomUniform(Initializer):
    """Initializer that generates tensors with a uniform distribution.

    # Arguments
        minval: A python scalar or a scalar tensor. Lower bound of the range
          of random values to generate.
        maxval: A python scalar or a scalar tensor. Upper bound of the range
          of random values to generate.  Defaults to 1 for float types.
        seed: A Python integer. Used to seed the random generator.
    """

    def __init__(self, minval=-0.05, maxval=0.05, seed=None):
        self.minval = minval
        self.maxval = maxval
        self.seed = seed

    def __call__(self, shape, dtype=None):
        return K.random_uniform(shape, self.minval, self.maxval,
                                dtype=dtype, seed=self.seed)

    def get_config(self):
        return {
            'minval': self.minval,
            'maxval': self.maxval,
            'seed': self.seed,
        }


class TruncatedNormal(Initializer):
    """Initializer that generates a truncated normal distribution.

    These values are similar to values from a `random_normal_initializer`
    except that values more than two standard deviations from the mean
    are discarded and re-drawn. This is the recommended initializer for
    neural network weights and filters.

    # Arguments
        mean: a python scalar or a scalar tensor. Mean of the random values
          to generate.
        stddev: a python scalar or a scalar tensor. Standard deviation of the
          random values to generate.
        seed: A Python integer. Used to seed the random generator.
    """

    def __init__(self, mean=0., stddev=0.05, seed=None):
        self.mean = mean
        self.stddev = stddev
        self.seed = seed

    def __call__(self, shape, dtype=None):
        return K.truncated_normal(shape, self.mean, self.stddev,
                                  dtype=dtype, seed=self.seed)

    def get_config(self):
        return {
            'mean': self.mean,
            'stddev': self.stddev,
            'seed': self.seed
        }


class VarianceScaling(Initializer):
    """Initializer capable of adapting its scale to the shape of weights.

    With `distribution="normal"`, samples are drawn from a truncated normal
    distribution centered on zero, with `stddev = sqrt(scale / n)` where n is:
        - number of input units in the weight tensor, if mode = "fan_in"
        - number of output units, if mode = "fan_out"
        - average of the numbers of input and output units, if mode = "fan_avg"

    With `distribution="uniform"`,
    samples are drawn from a uniform distribution
    within [-limit, limit], with `limit = sqrt(3 * scale / n)`.

    # Arguments
        scale: Scaling factor (positive float).
        mode: One of "fan_in", "fan_out", "fan_avg".
        distribution: Random distribution to use. One of "normal", "uniform".
        seed: A Python integer. Used to seed the random generator.

    # Raises
        ValueError: In case of an invalid value for the "scale", mode" or
          "distribution" arguments.
    """

    def __init__(self, scale=1.0,
                 mode='fan_in',
                 distribution='normal',
                 seed=None):
        if scale <= 0.:
            raise ValueError('`scale` must be a positive float. Got:', scale)
        mode = mode.lower()
        if mode not in {'fan_in', 'fan_out', 'fan_avg'}:
            raise ValueError('Invalid `mode` argument: '
                             'expected on of {"fan_in", "fan_out", "fan_avg"} '
                             'but got', mode)
        distribution = distribution.lower()
        if distribution not in {'normal', 'uniform'}:
            raise ValueError('Invalid `distribution` argument: '
                             'expected one of {"normal", "uniform"} '
                             'but got', distribution)
        self.scale = scale
        self.mode = mode
        self.distribution = distribution
        self.seed = seed

    def __call__(self, shape, dtype=None):
        fan_in, fan_out = _compute_fans(shape)
        scale = self.scale
        if self.mode == 'fan_in':
            scale /= max(1., fan_in)
        elif self.mode == 'fan_out':
            scale /= max(1., fan_out)
        else:
            scale /= max(1., float(fan_in + fan_out) / 2)
        if self.distribution == 'normal':
            stddev = np.sqrt(scale)
            return K.truncated_normal(shape, 0., stddev,
                                      dtype=dtype, seed=self.seed)
        else:
            limit = np.sqrt(3. * scale)
            return K.random_uniform(shape, -limit, limit,
                                    dtype=dtype, seed=self.seed)

    def get_config(self):
        return {
            'scale': self.scale,
            'mode': self.mode,
            'distribution': self.distribution,
            'seed': self.seed
        }


class Orthogonal(Initializer):
    """Initializer that generates a random orthogonal matrix.

    # Arguments
        gain: Multiplicative factor to apply to the orthogonal matrix.
        seed: A Python integer. Used to seed the random generator.

    # References
        Saxe et al., http://arxiv.org/abs/1312.6120
    """

    def __init__(self, gain=1., seed=None):
        self.gain = gain
        self.seed = seed

    def __call__(self, shape, dtype=None):
        num_rows = 1
        for dim in shape[:-1]:
            num_rows *= dim
        num_cols = shape[-1]
        flat_shape = (num_rows, num_cols)
        if self.seed is not None:
            np.random.seed(self.seed)
        a = np.random.normal(0.0, 1.0, flat_shape)
        u, _, v = np.linalg.svd(a, full_matrices=False)
        # Pick the one with the correct shape.
        q = u if u.shape == flat_shape else v
        q = q.reshape(shape)
        return self.gain * q[:shape[0], :shape[1]]

    def get_config(self):
        return {
            'gain': self.gain,
            'seed': self.seed
        }


class ConvolutionAware(Initializer):
    """
    Initializer that generates orthogonal convolution filters in the fourier
    space. If this initializer is passed a shape that is not 3D or 4D,
    orthogonal intialization will be used.

    # Arguments
        eps_std: Standard deviation for the random normal noise used to break
        symmetry in the inverse fourier transform.
        seed: A Python integer. Used to seed the random generator.
    # References
        Armen Aghajanyan, https://arxiv.org/abs/1702.06295
    """

    def __init__(self, eps_std=0.05, seed=None):
        self.eps_std = eps_std
        self.seed = seed
        self.orthogonal = Orthogonal()

    def __call__(self, shape):
        rank = len(shape)

        fan_in, fan_out = _compute_fans(shape, K.image_data_format())
        variance = 2 / fan_in

        if rank == 3:
            row, stack_size, filters_size = shape

            transpose_dimensions = (2, 1, 0)
            kernel_shape = (row,)
            correct_fft = lambda shape, s=[None]: np.fft.irfft(shape, s[0])

        elif rank == 4:
            row, column, stack_size, filters_size = shape
            print(row, column, stack_size, filters_size)
            transpose_dimensions = (2, 3, 1, 0)
            kernel_shape = (row, column)
            correct_fft = np.fft.irfft2

        else:
            return self.orthogonal(shape)

        kernel_fourier_shape = correct_fft(np.zeros(kernel_shape)).shape
        init = []
        for i in range(filters_size):
            basis = self._create_basis(
                stack_size, np.prod(kernel_fourier_shape))
            basis = basis.reshape((stack_size,) + kernel_fourier_shape)

            filters = [correct_fft(x, kernel_shape) +
                       np.random.normal(0, self.eps_std, kernel_shape) for
                       x in basis]

            init.append(filters)

        # Format of array is now: filters, stack, row, column
        init = np.array(init, dtype=K.floatx())
        init = self._scale_filters(init, variance)
        return init.transpose(transpose_dimensions)

    def _create_basis(self, filters, size):
        if size == 1:
            return np.random.normal(0.0, self.eps_std, (filters, size))

        nbb = filters // size + 1
        li = []
        for i in range(nbb):
            a = np.random.normal(0.0, 1.0, (size, size))
            a = self._symmetrize(a)
            u, _, v = np.linalg.svd(a)
            li.extend(u.T.tolist())
        p = np.array(li[:filters], dtype=K.floatx())
        return p

    def _symmetrize(self, a):
        return a + a.T - np.diag(a.diagonal())

    def _scale_filters(self, filters, variance):
        c_var = np.var(filters)
        p = np.sqrt(variance / c_var)
        return filters * p

    def get_config(self):
        return {
            'eps_std': self.eps_std,
            'seed': self.seed
        }


class Identity(Initializer):
    """Initializer that generates the identity matrix.

    Only use for square 2D matrices.

    # Arguments
        gain: Multiplicative factor to apply to the identity matrix.
    """

    def __init__(self, gain=1.):
        self.gain = gain

    def __call__(self, shape, dtype=None):
        if len(shape) != 2 or shape[0] != shape[1]:
            raise ValueError('Identity matrix initializer can only be used '
                             'for 2D square matrices.')
        else:
            return self.gain * np.identity(shape[0])

    def get_config(self):
        return {
            'gain': self.gain
        }


def lecun_uniform(seed=None):
    """LeCun uniform initializer.

    It draws samples from a uniform distribution within [-limit, limit]
    where `limit` is `sqrt(3 / fan_in)`
    where `fan_in` is the number of input units in the weight tensor.

    # Arguments
        seed: A Python integer. Used to seed the random generator.

    # Returns
        An initializer.

    # References
        LeCun 98, Efficient Backprop,
        http://yann.lecun.com/exdb/publis/pdf/lecun-98b.pdf
    """
    return VarianceScaling(scale=1.,
                           mode='fan_in',
                           distribution='uniform',
                           seed=seed)


def glorot_normal(seed=None):
    """Glorot normal initializer, also called Xavier normal initializer.

    It draws samples from a truncated normal distribution centered on 0
    with `stddev = sqrt(2 / (fan_in + fan_out))`
    where `fan_in` is the number of input units in the weight tensor
    and `fan_out` is the number of output units in the weight tensor.

    # Arguments
        seed: A Python integer. Used to seed the random generator.

    # Returns
        An initializer.

    # References
        Glorot & Bengio, AISTATS 2010
        http://jmlr.org/proceedings/papers/v9/glorot10a/glorot10a.pdf
    """
    return VarianceScaling(scale=1.,
                           mode='fan_avg',
                           distribution='normal',
                           seed=seed)


def glorot_uniform(seed=None):
    """Glorot uniform initializer, also called Xavier uniform initializer.

    It draws samples from a uniform distribution within [-limit, limit]
    where `limit` is `sqrt(6 / (fan_in + fan_out))`
    where `fan_in` is the number of input units in the weight tensor
    and `fan_out` is the number of output units in the weight tensor.

    # Arguments
        seed: A Python integer. Used to seed the random generator.

    # Returns
        An initializer.

    # References
        Glorot & Bengio, AISTATS 2010
        http://jmlr.org/proceedings/papers/v9/glorot10a/glorot10a.pdf
    """
    return VarianceScaling(scale=1.,
                           mode='fan_avg',
                           distribution='uniform',
                           seed=seed)


def he_normal(seed=None):
    """He normal initializer.

    It draws samples from a truncated normal distribution centered on 0
    with `stddev = sqrt(2 / fan_in)`
    where `fan_in` is the number of input units in the weight tensor.

    # Arguments
        seed: A Python integer. Used to seed the random generator.

    # Returns
        An initializer.

    # References
        He et al., http://arxiv.org/abs/1502.01852
    """
    return VarianceScaling(scale=2.,
                           mode='fan_in',
                           distribution='normal',
                           seed=seed)


def he_uniform(seed=None):
    """He uniform variance scaling initializer.

    It draws samples from a uniform distribution within [-limit, limit]
    where `limit` is `sqrt(6 / fan_in)`
    where `fan_in` is the number of input units in the weight tensor.

    # Arguments
        seed: A Python integer. Used to seed the random generator.

    # Returns
        An initializer.

    # References
        He et al., http://arxiv.org/abs/1502.01852
    """
    return VarianceScaling(scale=2.,
                           mode='fan_in',
                           distribution='uniform',
                           seed=seed)


# Compatibility aliases

zero = zeros = Zeros
one = ones = Ones
constant = Constant
uniform = random_uniform = RandomUniform
normal = random_normal = RandomNormal
truncated_normal = TruncatedNormal
identity = Identity
orthogonal = Orthogonal
cai = CAI = ConvolutionAware

# Utility functions


def _compute_fans(shape, data_format='channels_last'):
    """Computes the number of input and output units for a weight shape.

    # Arguments
        shape: Integer shape tuple.
        data_format: Image data format to use for convolution kernels.
            Note that all kernels in Keras are standardized on the
            `channels_last` ordering (even when inputs are set
            to `channels_first`).

    # Returns
        A tuple of scalars, `(fan_in, fan_out)`.

    # Raises
        ValueError: in case of invalid `data_format` argument.
    """
    if len(shape) == 2:
        fan_in = shape[0]
        fan_out = shape[1]
    elif len(shape) in {3, 4, 5}:
        # Assuming convolution kernels (1D, 2D or 3D).
        # TH kernel shape: (depth, input_depth, ...)
        # TF kernel shape: (..., input_depth, depth)
        if data_format == 'channels_first':
            receptive_field_size = np.prod(shape[2:])
            fan_in = shape[1] * receptive_field_size
            fan_out = shape[0] * receptive_field_size
        elif data_format == 'channels_last':
            receptive_field_size = np.prod(shape[:2])
            fan_in = shape[-2] * receptive_field_size
            fan_out = shape[-1] * receptive_field_size
        else:
            raise ValueError('Invalid data_format: ' + data_format)
    else:
        # No specific assumptions.
        fan_in = np.sqrt(np.prod(shape))
        fan_out = np.sqrt(np.prod(shape))
    return fan_in, fan_out


def serialize(initializer):
    return serialize_keras_object(initializer)


def deserialize(config, custom_objects=None):
    return deserialize_keras_object(config,
                                    module_objects=globals(),
                                    custom_objects=custom_objects,
                                    printable_module_name='initializer')


def get(identifier):
    if isinstance(identifier, dict):
        return deserialize(identifier)
    elif isinstance(identifier, six.string_types):
        config = {'class_name': str(identifier), 'config': {}}
        return deserialize(config)
    elif callable(identifier):
        return identifier
    else:
        raise ValueError('Could not interpret initializer identifier:',
                         identifier)
