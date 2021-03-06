import json

import numpy as np
from python_speech_features import mfcc
import scipy.io.wavfile as wav

def make_equal_dim(feature1, feature2, diff):
	if diff > 0:
		# Feature1 is bigger
		return feature1[:-diff], feature2
	else:
		return feature1, feature2[:diff]

def get_audio_visual_feature_vector(audio_file_path, json_file_path, numcep, numcontext):
	"""
	Args:
		1. audio_file_path: File path for audio file (.wav file)
		2. json_file_path: File path for JSON file storing visual features. 
		3. numcep: Number of units in initial layer of neural network.
			In case of audio-only model: numcep = 26
			In case of AVSR model: numcep = 26+50 = 76
		4. numcontext: Determines window size for adding context info to each individual value.
	"""

	with open(json_file_path, 'r') as f:
		data = json.loads(f.read())
		file_name = data['name']
		visual_feature = np.array(data['encoded'])

	# `visual_feature` is a numpy array which stores visual bottleneck features for each split .wav audio file.
	# Shape of `visual_feature` = (x, y)
	# Here, x = number of video frames to be used for training.
	# And y = size of encodings(for each frame) extracted from our deep autoencoder.
	# In our case y = 50
	# Please see `util.data_preprocessing_video.py` for more details.

	# Load wav file
	fs, audio = wav.read(audio_file_path)

	# Get mfcc coefficients
	orig_inputs = mfcc(audio, samplerate=fs, numcep=26, winstep=0.03334)
	# For our video, expected frame rate is 30, or time difference between each frame is 0.03334s(approx).
	# The above function returns MFCC features at every 0.03334s time step.
	# For having equal audio and visual features, we must extract MFCC features after every 0.03334 secs.

	# We only keep every 2nd feature (BiRNN stride = 2)
	orig_inputs = orig_inputs[::2]
	
	if len(orig_inputs) != visual_feature.shape[0]:
		orig_inputs, visual_feature = make_equal_dim(
										orig_inputs, visual_feature, 
										len(orig_inputs) - visual_feature.shape[0])
	
	orig_inputs = (orig_inputs - np.mean(orig_inputs))/np.std(orig_inputs)
	visual_feature = (visual_feature - np.mean(visual_feature))/np.std(visual_feature)
	modified_inputs = np.hstack((orig_inputs, visual_feature))

	# The next section of code is mostly similar to the one in `util.audio.audiofile_to_input_vector()` func.

	# For each time slice of the training set, we need to copy the context this makes
	# the numcep dimensions vector into a numcep + 2*numcep*numcontext dimensions
	# because of:
	#  - numcep dimensions for the current mfcc feature set
	#  - numcontext*numcep dimensions for each of the past and future (x2) mfcc feature set
	# => so numcep + 2*numcontext*numcep
	train_inputs = np.array([], np.float32)
	train_inputs.resize((modified_inputs.shape[0], numcep + 2*numcep*numcontext))

	empty_feature = np.array([])
	empty_feature.resize((numcep))

	# Prepare train_inputs with past and future contexts
	time_slices = list(range(train_inputs.shape[0]))
	context_past_min   = time_slices[0]  + numcontext
	context_future_max = time_slices[-1] - numcontext
	for time_slice in time_slices:
		### Reminder: array[start:stop:step]
		### slices from indice |start| up to |stop| (not included), every |step|
		# Pick up to numcontext time slices in the past, and complete with empty visual features
		need_empty_past     = max(0, (context_past_min - time_slice))
		empty_source_past   = list(empty_feature for empty_slots in range(need_empty_past))
		data_source_past    = modified_inputs[max(0, time_slice - numcontext):time_slice]
		assert(len(empty_source_past) + len(data_source_past) == numcontext)

		# Pick up to numcontext time slices in the future, and complete with empty visual features
		need_empty_future   = max(0, (time_slice - context_future_max))
		empty_source_future = list(empty_feature for empty_slots in range(need_empty_future))
		data_source_future  = modified_inputs[time_slice + 1:time_slice + numcontext + 1]
		assert(len(empty_source_future) + len(data_source_future) == numcontext)

		if need_empty_past:
			past   = np.concatenate((empty_source_past, data_source_past))
		else:
			past   = data_source_past

		if need_empty_future:
			future = np.concatenate((data_source_future, empty_source_future))
		else:
			future = data_source_future

		past   = np.reshape(past, numcontext*numcep)
		now    = modified_inputs[time_slice]
		future = np.reshape(future, numcontext*numcep)

		train_inputs[time_slice] = np.concatenate((past, now, future))
		assert(len(train_inputs[time_slice]) == numcep + 2*numcep*numcontext)

	# Return final train inputs
	return train_inputs

