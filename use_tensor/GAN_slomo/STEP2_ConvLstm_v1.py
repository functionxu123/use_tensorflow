'''
Created on Sep 27, 2019

@author: sherl
'''
import tensorflow as tf
from data import create_dataset2 as cdata
import numpy as np
import cv2, os, random, time
from dask.array.tests.test_numpy_compat import dtype

#图像形状 
img_size_w=int (640/2)
img_size_h=int (360/2)
img_size=[img_size_h, img_size_w]

flow_size_w = img_size_w
flow_size_h = img_size_h
flow_size = [flow_size_h, flow_size_w]
flow_channel = 2
input_channel=flow_channel*2

#kernel concern
output_channel = 12
batchsize = 1  # 分别对应正向和反向光流
kernel_len = 3

state_shape=[batchsize, flow_size_h, flow_size_w, output_channel]

#数据输入的样式，一套3个图，每个图3channel，前后帧和t时刻帧 
group_img_num=3
img_channel=3


timestep = 12

#hyper param 
dropout=0.5 
leakyrelurate=0.2
stddev=0.01
bias_init=0.0
LR=1e-3



modelpath = "/home/sherl/Pictures/v24/GAN_2019-08-20_21-49-57_base_lr-0.000200_batchsize-12_maxstep-240000_fix_a_bug_BigProgress"
meta_name = r'model_keep-239999.meta'

# 设置GPU显存按需增长
gpu_options = tf.GPUOptions(allow_growth=True)
config = tf.ConfigProto(gpu_options=gpu_options)


class Step2_ConvLstm:

    def __init__(self, sess):
        self.sess = sess
        
        # 注意这里的placeholder
        self.input_pla = tf.placeholder(tf.float32, [batchsize,  flow_size_h, flow_size_w, input_channel], name='step2_opticalflow_in')
        
        self.state_pla_c = tf.placeholder(tf.float32, state_shape, name='step2_state_in_c')
        self.state_pla_h = tf.placeholder(tf.float32, state_shape, name='step2_state_in_h')
        
        self.imgs_pla = tf.placeholder(tf.float32, [batchsize, img_size_h, img_size_w, group_img_num*img_channel], name='step2_oriimgs_in')
        self.frame0=self.imgs_pla[:,:,:,:img_channel]
        self.frame1=self.imgs_pla[:,:,:,img_channel:img_channel*2]
        self.frame2=self.imgs_pla[:,:,:,img_channel*2:]
        
        self.timerates_pla=tf.placeholder(tf.float32, [batchsize], name='step2_inner_timerates_in')
        self.timerates_expand=tf.expand_dims(self.timerates_pla, -1)
        self.timerates_expand=tf.expand_dims(self.timerates_expand, -1)
        self.timerates_expand=tf.expand_dims(self.timerates_expand, -1) #batchsize*1*1*1
        
        self.cell = tf.contrib.rnn.ConvLSTMCell(conv_ndims=2, input_shape=[flow_size_h, flow_size_w, input_channel], \
                                                output_channels=output_channel, kernel_shape=[kernel_len, kernel_len])
        
        self.state_init = self.cell.zero_state(batch_size=batchsize, dtype=tf.float32)
        self.state_init_np=( np.zeros(state_shape, dtype=np.float32), np.zeros(state_shape, dtype=np.float32) )
        
        print (self.state_init) #LSTMStateTuple(c=<tf.Tensor 'ConvLSTMCellZeroState/zeros:0' shape=(2, 180, 320, 12) dtype=float32>, h=<tf.Tensor 'ConvLSTMCellZeroState/zeros_1:0' shape=(2, 180, 320, 12) dtype=float32>)
        
        self.output,self.state_final=self.cell.call(inputs=self.input_pla,state=(self.state_pla_c, self.state_pla_h) )
        print (self.output)  #Tensor("mul_2:0", shape=(2, 180, 320, 12), dtype=float32)
        
        self.flow_after=self.final_convlayer(self.output)
        print (self.flow_after) #Tensor("final_convlayer/BiasAdd:0", shape=(2, 180, 320, 4), dtype=float32)
        
        self.opticalflow_0_2=tf.slice(self.flow_after, [0, 0, 0, 0], [-1, -1, -1, 2], name='step2_opticalflow_0_2')
        self.opticalflow_2_0=tf.slice(self.flow_after, [0, 0, 0, 2], [-1, -1, -1, 2], name='step2_opticalflow_2_0')
        print ('original flow:',self.opticalflow_0_2, self.opticalflow_2_0)
        
        #反向光流算中间帧
        self.opticalflow_t_0=tf.add( -(1-self.timerates_expand)*self.timerates_expand*self.opticalflow_0_2 ,\
                                      self.timerates_expand*self.timerates_expand*self.opticalflow_2_0 , name="step2_opticalflow_t_0")
        self.opticalflow_t_2=tf.add( (1-self.timerates_expand)*(1-self.timerates_expand)*self.opticalflow_0_2 ,\
                                      self.timerates_expand*(self.timerates_expand-1)*self.opticalflow_2_0, name="step2_opticalflow_t_2")
        
        print ('two optical flow:',self.opticalflow_t_0, self.opticalflow_t_2)
        
        #2种方法合成t时刻的帧
        self.img_flow_2_t=self.warp_op(self.frame2, -self.opticalflow_t_2) #!!!
        self.img_flow_0_t=self.warp_op(self.frame0, -self.opticalflow_t_0) #!!!
        
        self.G_net=tf.add(self.timerates_expand*self.img_flow_2_t , (1-self.timerates_expand)*self.img_flow_0_t, name="step2_net_generate" )
        
        #利用光流前后帧互相合成
        self.img_flow_2_0=self.warp_op(self.frame2, self.opticalflow_2_0)  #frame2->frame0
        self.img_flow_0_2=self.warp_op(self.frame0, self.opticalflow_0_2)  #frame0->frame2
        
        
        #1、contex loss
        print ("forming conx loss：")
        tep_G_shape=self.G_net.get_shape().as_list()[1:]
        
        self.contex_Genera =tf.keras.applications.VGG16(include_top=False, input_tensor=self.G_net,  input_shape=tep_G_shape).get_layer("block4_conv3").output
        self.contex_frame1 =tf.keras.applications.VGG16(include_top=False, input_tensor=self.frame1, input_shape=tep_G_shape).get_layer("block4_conv3").output
        
        self.contex_loss=   tf.reduce_mean(tf.squared_difference( self.contex_frame1, self.contex_Genera), name='step2_Contex_loss')
        print ('step2_loss_mean_contex form finished..')
        
        
        #2、L1 loss
        print ("forming L1 loss:生成帧与GT、frame2->frame0与frame0、frame0->frame2与frame2")
        self.L1_loss_interframe =tf.reduce_mean(tf.abs(  self.G_net-self.frame1  ))
        self.L1_loss_all        =tf.reduce_mean(tf.abs(  self.G_net-self.frame1  ) + \
                                                tf.abs(self.img_flow_2_0-self.frame0) + \
                                                tf.abs(self.img_flow_0_2-self.frame2), name='G_clear_l1_loss')
        #self.G_loss_mean_Square=  self.contex_loss*1 + self.L1_loss_all
        print ('step2_loss_mean_l1 form finished..')
        
        #6 SSIM
        self.ssim = tf.image.ssim(self.G_net, self.frame1, max_val=2.0)
        print ("ssim:",self.ssim)  #ssim: Tensor("Mean_10:0", shape=(12,), dtype=float32)
        
        #7 PSNR
        self.psnr = tf.image.psnr(self.G_net, self.frame1, max_val=2.0, name="step2_frame1_psnr")
        print ("psnr:", self.psnr) #psnr: Tensor("G_frame1_psnr/Identity_3:0", shape=(12,), dtype=float32)
        
        
        self.G_loss_all=self.contex_loss + self.L1_loss_all
        
        self.train_op = tf.train.AdamOptimizer(LR).minimize(self.G_loss_all)
        
        
        
        
        
        
        
        
        
        
        
        #最后构建完成后初始化参数 
        self.sess.run(tf.global_variables_initializer())
        
        
    #最终输出加上一个conv层才是得到的光流
    def final_convlayer(self, inputdata, filterlen=kernel_len, outchannel=flow_channel*2,   scopename="final_convlayer"):
        inputshape=inputdata.get_shape().as_list()
        
        with tf.variable_scope(scopename,  reuse=tf.AUTO_REUSE) as scope: 
            kernel=tf.get_variable('weights', [filterlen,filterlen, inputshape[-1], outchannel], dtype=tf.float32, \
                                   initializer=tf.random_normal_initializer(stddev=stddev))
            #tf.nn.conv2d中的filter参数，是[filter_height, filter_width, in_channels, out_channels]的形式，
                    
            ret=tf.nn.conv2d(inputdata, kernel, strides=[1,1,1,1], padding="SAME")
                    
            bias=tf.get_variable('bias', [outchannel], dtype=tf.float32, initializer=tf.constant_initializer(bias_init))
            ret=tf.nn.bias_add(ret, bias)
        return ret
        
        
        
        

    def forward_once(self, image_3, state, timerate=0.5):
        output, state_new=self.sess.run([self.output,self.state_final], \
                      feed_dict={self.input_pla:inputs,  self.state_pla_c:state[0],  self.state_pla_h:state[1]})
        
        print (output.shape, type(state_new) )
        
        return output,state_new





if __name__ == '__main__':   
    with tf.Session(config=config) as sess:     
        step2 = Step2_ConvLstm(sess)
        step2.forward_once(np.random.rand(batchsize,  flow_size_h, flow_size_w, input_channel), state=step2.state_init_np)

        
        
        
        
        
        
        
        
        
        
        
        
        
