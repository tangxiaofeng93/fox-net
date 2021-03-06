import datetime
import json
import numpy as np
import os
import sys
import tensorflow as tf

from foxnet_model import FoxNetModel
from data_manager import DataManager
from scipy.misc import imresize


# COMMAND LINE ARGUMENTS
tf.app.flags.DEFINE_bool("dev", False, "")
tf.app.flags.DEFINE_bool("test", False, "")
tf.app.flags.DEFINE_string("model", "fc", "Options: fc, simple_cnn, dqn, dqn_3d")
tf.app.flags.DEFINE_bool("validate", True, "Validate after all training is complete")
tf.app.flags.DEFINE_bool("validate_incrementally", False, "Validate after every epoch")
tf.app.flags.DEFINE_integer("num_images", 1000, "")
tf.app.flags.DEFINE_float("eval_proportion", 0.2, "")
tf.app.flags.DEFINE_bool("plot", True, "")
tf.app.flags.DEFINE_bool("verbose", False, "")

tf.app.flags.DEFINE_bool("load_model", False, "")
tf.app.flags.DEFINE_bool("save_model", True, "")
tf.app.flags.DEFINE_string("model_dir", "sample_model", "Directory with a saved model's files.")
tf.app.flags.DEFINE_bool("train_offline", False, "")
tf.app.flags.DEFINE_bool("train_online", False, "")
tf.app.flags.DEFINE_bool("qlearning", False, "")
tf.app.flags.DEFINE_bool("user_overwrite", False, "")
tf.app.flags.DEFINE_string("ip", "127.0.0.1", "Specify host IP. Default is local loopback.")
# LAYER SIZES
tf.app.flags.DEFINE_integer("cnn_filter_size", 7, "Size of filter.")
tf.app.flags.DEFINE_integer("cnn_num_filters", 32, "Filter count.")

# HYPERPARAMETERS
tf.app.flags.DEFINE_integer("frames_per_state", 1, "")
tf.app.flags.DEFINE_float("lr", 0.000004, "Learning rate.")
tf.app.flags.DEFINE_float("dropout", .5, "For simple_cnn only; 0.1 would drop out 10 percent of input units")
tf.app.flags.DEFINE_float("reg_lambda", .01, "Regularization")
tf.app.flags.DEFINE_integer("num_epochs", 20, "")
tf.app.flags.DEFINE_float("epsilon", 0.05, "E-greedy exploration rate.")

tf.app.flags.DEFINE_bool("use_target_net", False, "")
tf.app.flags.DEFINE_float("tau", 0.001, "Soft target update factor.")
tf.app.flags.DEFINE_integer("target_q_update_step", 10, "")

# INFRASTRUCTURE
tf.app.flags.DEFINE_string("data_dir", "./data/data_053017/", "data directory (default ./data)")
tf.app.flags.DEFINE_string("results_dir", "./results/", "")
tf.app.flags.DEFINE_integer("image_width", 64, "")
tf.app.flags.DEFINE_integer("image_height", 48, "")
tf.app.flags.DEFINE_integer("num_channels", 3, "")
tf.app.flags.DEFINE_integer("batch_size", 10, "")
tf.app.flags.DEFINE_integer("replay_buffer_size", 1000, "")

ACTIONS = ['w', 'a', 's', 'd', 'j', 'k', 'n']
ACTION_NAMES = ['up', 'left', 'down', 'right', 'fire', 'back', 'do nothing']

FLAGS = tf.app.flags.FLAGS

def initialize_model(session, model):
    print("##### MODEL ###############################################")
    session.run(tf.global_variables_initializer())
    print('Num params: %d' % sum(v.get_shape().num_elements() for v in tf.trainable_variables()))
    print("Flags: " + str(FLAGS.__flags))
    return model

def record_params():
    dt = str(datetime.datetime.now())
    # Record params
    f = open(FLAGS.results_dir + "params" + "/" + dt + ".txt","w+")
    f.write(" ".join(sys.argv) + "\n\n")
    for flag in FLAGS.__flags:
        f.write(flag + ":" + str(FLAGS.__flags[flag]) + "\n")
    f.close()
    # Dump flags in case we want to load this model later
    with open(FLAGS.results_dir + "flags" + "/" + dt + ".json","w+") as f:
        json.dump(FLAGS.__flags, f)
    return dt

def run_model():
    # Reset every time
    tf.reset_default_graph()
    tf.set_random_seed(1)

    # Get the session.
    session = tf.Session()

    # Initialize a FoxNet model.
    foxnet = FoxNetModel(
                FLAGS.model,
                FLAGS.qlearning,
                FLAGS.lr,
                FLAGS.reg_lambda,
                FLAGS.dropout,
                FLAGS.use_target_net,
                FLAGS.tau,
                FLAGS.target_q_update_step,
                FLAGS.image_height,
                FLAGS.image_width,
                FLAGS.num_channels,
                FLAGS.frames_per_state,
                ACTIONS,
                ACTION_NAMES,
                FLAGS.cnn_filter_size,
                FLAGS.cnn_num_filters
            )

    foxnet.saver = tf.train.Saver(max_to_keep = 3, keep_checkpoint_every_n_hours=4)
    model_dir = './models/%s' % (FLAGS.model_dir)
    model_name = '%s' % (FLAGS.model_dir)
    model_path = model_dir + '/' + model_name

    initialize_model(session, foxnet)

    dt = record_params()

    # Initialize a data manager.
    data_manager = DataManager(FLAGS.verbose)
    if FLAGS.train_online:
        frames_per_state = 1
        if FLAGS.model == "dqn_3d":
            frames_per_state = FLAGS.frames_per_state
        data_manager.init_online(foxnet, session, FLAGS.batch_size, FLAGS.replay_buffer_size, frames_per_state,
                                 FLAGS.ip, FLAGS.image_height, FLAGS.image_width, FLAGS.epsilon, FLAGS.user_overwrite)
    else:
        data_manager.init_offline(FLAGS.test, get_data_params(), FLAGS.batch_size)

    # Load pretrained model
    if FLAGS.load_model:
        # Create an object to get emulator frames
        # frame_reader = FrameReader(FLAGS.ip, FLAGS.image_height, FLAGS.image_width)

        # Load the model
        model_dir = './models/%s/' % (FLAGS.model_dir)
        model_name = '%s' % (FLAGS.model_dir)
        print('Loading model from dir: %s' % model_dir)
        foxnet.saver.restore(session, tf.train.latest_checkpoint(model_dir))
        # sv = tf.train.Supervisor(logdir=model_dir)
        # with sv.managed_session() as session:

            # if not sv.should_stop():
            #     if FLAGS.train_online == True:
            #         foxnet.run_q_learning(data_manager, session)
    else:
        # Train a new model.
       
        print("dt = " + dt)

        print("##### TRAINING ############################################")
        # Run Q-learning or classification.
        if FLAGS.qlearning:
            foxnet.run_q_learning(data_manager, session, FLAGS.num_epochs, model_path, save_model=FLAGS.save_model, results_dir=FLAGS.results_dir,
                                  plot=FLAGS.plot, dt=dt)
        else:
            foxnet.run_classification(data_manager,
                                      session,
                                      epochs=FLAGS.num_epochs,
                                      model_path=model_path,
                                      save_model=FLAGS.save_model,
                                      training_now=True,
                                      validate_incrementally=FLAGS.validate_incrementally,
                                      print_every=1,
                                      plot=FLAGS.plot,
                                      results_dir=FLAGS.results_dir,
                                      dt=dt
                                      )

    # Save the model
    if FLAGS.save_model:
        # Save model
        model_dir = './models/%s' % (FLAGS.model_dir)
        model_name = '%s' % (FLAGS.model_dir)
        if not os.path.exists(model_dir):
            os.makedirs(model_dir)
        foxnet.saver.save(session, model_dir + '/' + model_name)
        print('Saved model to dir: %s' % model_dir)

    # Validate the model
    if (FLAGS.validate and not FLAGS.train_online and not FLAGS.qlearning):
        print("##### VALIDATING ##########################################")
        foxnet.run_validation(data_manager, session, confusion=True, results_dir=FLAGS.results_dir, dt=dt)

    # Close session
    session.close()

def get_data_params():
    return {
        "data_dir": FLAGS.data_dir,
        "num_images": FLAGS.num_images,
        "width": FLAGS.image_width,
        "height": FLAGS.image_height,
        "multi_frame_state": FLAGS.model == "dqn_3d",
        "frames_per_state": FLAGS.frames_per_state,
        "actions": ACTIONS,
        "eval_proportion": FLAGS.eval_proportion,
        "image_size": 28,
    }

def main(_):
    # TODO: Eventually, should have separate dev and test datasets and require that we specify which we want to use.
    # assert(FLAGS.validate or ((FLAGS.dev and not FLAGS.test) or (FLAGS.test and not FLAGS.dev))), "When not validating, must set exaclty one of --dev or --test flag to specify evaluation dataset."

    # Set random seed
    np.random.seed(244)

    # Train model
    run_model()

if __name__ == "__main__":
    tf.app.run()
