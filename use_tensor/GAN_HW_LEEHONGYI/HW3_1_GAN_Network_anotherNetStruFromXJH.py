#coding:utf-8
'''
Created on 2018年12月10日

@author: sherl
'''
import cv2,os,random,time
from datetime import datetime
import os.path as op
from PIL import Image
import matplotlib.pyplot as plt
import numpy as np
import tensorflow as tf
import HW3_1_gen_anime_tfrecord as anime_data


#!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!

TIMESTAMP = "{0:%Y-%m-%d_%H-%M-%S}".format(datetime.now())


train_size=33431 #训练集规模
batchsize=128
noise_size=100
img_size=96

base_lr=0.0002 #基础学习率
beta1=0.5

maxstep=1600000 #训练多少次
eval_step=int (train_size/batchsize)

decay_steps=10000
decay_rate=0.99

incase_div_zero=1e-10  #这个值大一些可以避免d训得太好，也避免了g梯度

G_first_channel=64
D_first_channel=64

logdir="./logs/GAN_"+TIMESTAMP+('_base_lr-%f_batchsize-%d_maxstep-%d'%(base_lr,batchsize, maxstep))

bigimgsdir=op.join(logdir, 'randomimgs')
if not op.exists(bigimgsdir): os.makedirs(bigimgsdir)
#!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!


class GAN_Net:
    def __init__(self, sess):
        self.sess=sess
        self.tf_inimg=anime_data.read_tfrecord_batch( batchsize=batchsize, imgsize=img_size)  #tensor的img输入
        self.global_step = tf.Variable(0, name='global_step', trainable=False)
        
        self.G_para=[]
        self.D_para=[]       
        self.dropout=0.5 
        self.leakyrelurate=0.2
        self.stddev=0.02
        self.bias_init=0.0
        
        #for debug
        self.cnt_tep=0
        self.deb_kep=0
        self.deb_kep2=0
        
        #3个placeholder， img和noise,training 
        self.noise_pla=tf.placeholder(tf.float32, [batchsize, noise_size], name='noise_in')
        self.imgs_pla = tf.placeholder(tf.float32, [batchsize, img_size, img_size, 3], name='imgs_in')
        self.training=tf.placeholder(tf.bool, name='training_in')
        
        
        #将g和d连起来看做一个网络，即给d输入fake imgs
        self.whole_net,self.D_fake_logit=self.Discriminator_net(self.Generator_net(self.noise_pla))
        #由于有重复构建网络结构的操作，这里重新清零保持weight的list，这样就能保障每个weight tensor只在list中出现一次

        self.G_net=self.Generator_net(self.noise_pla)
        self.D_net,self.D_real_logit=self.Discriminator_net(  self.img2tanh(self.tf_inimg)  ) #self.imgs_pla
        
        #还是应该以tf.trainable_variables()为主
        t_vars=tf.trainable_variables()
        print ("trainable vars cnt:",len(t_vars))
        self.G_para=[var for var in t_vars if var.name.startswith('G')]
        self.D_para=[var for var in t_vars if var.name.startswith('D')]
        
        '''
        print ('\nshow all trainable vars:',len(tf.trainable_variables()))
        for i in tf.trainable_variables():
            print (i)
        '''
        
        
        self.D_loss_mean,self.D_real_loss_mean, self.D_fake_loss_mean=self.D_loss()
        self.G_loss_mean=self.G_loss()
        self.train_D, self.train_D_real, self.train_D_fake=self.trainonce_D(decay_steps, decay_rate)
        self.train_G=self.trainonce_G(decay_steps, decay_rate)
        
        print ('\nfirst show G params')
        for ind,i in enumerate(self.G_para): print (ind,i)
        
        print('\nnext is D:\n')
        for ind,i in enumerate(self.D_para): print (ind,i)
        
        print ('\nnext is tf.GraphKeys.UPDATE_OPS:')
        print (tf.get_collection(tf.GraphKeys.UPDATE_OPS))
        
        self.summary_all=tf.summary.merge_all()
        init = tf.global_variables_initializer()#初始化tf.Variable,虽然后面会有初始化权重过程，但是最后一层是要根据任务来的,无法finetune，其参数需要随机初始化
        self.sess.run(init)
        
        
    def img2tanh(self,img):
        img=tf.cast(img,tf.float32)
        return img*2.0/255-1
    
            
    def D_loss(self):
        self.D_loss_fir=tf.nn.sigmoid_cross_entropy_with_logits(logits=self.D_real_logit, labels=tf.ones_like(self.D_net))   #real
        
        #下面是原来有问题的loss函数，探究下为什么有问题
        tep_real=tf.reduce_mean(tf.log(tf.maximum(self.D_net,incase_div_zero) )  )#real
        
        self.D_loss_sec=tf.nn.sigmoid_cross_entropy_with_logits(logits=self.D_fake_logit, labels=tf.zeros_like(self.whole_net))  #fake
        
        #下面是原来有问题的loss函数，探究下为什么有问题
        tep_fake=tf.reduce_mean( tf.log( tf.maximum(self.whole_net*(-1)+1,incase_div_zero)  ) ) #fake
        '''
        loss=tf.add_n([self.D_loss_fir,self.D_loss_sec] )
        #print ('loss shape:',loss.get_shape())
        loss_mean = tf.reduce_mean(loss, name='D_loss_mean')
        '''
        
        #testing target
        real_loss_mean=tf.reduce_mean(self.D_loss_fir)
        fake_loss_mean=tf.reduce_mean(self.D_loss_sec)
        tf.summary.scalar('D_DNET_loss_mean',real_loss_mean)
        tf.summary.scalar('D_WholeNet_loss_mean',fake_loss_mean)
        
        loss_mean=real_loss_mean+fake_loss_mean
        
        tf.summary.scalar('D_loss_mean',loss_mean)        
        ############################################################
        
        #下面是原来有问题的loss函数，探究下为什么有问题
        self.test_ori_loss_D=-(tep_fake+tep_real)
        
        return loss_mean,real_loss_mean,fake_loss_mean
        
    
    def G_loss(self):
        self.G_loss_fir=tf.nn.sigmoid_cross_entropy_with_logits(logits=self.D_fake_logit, labels=tf.ones_like(self.whole_net))
        loss_mean = tf.reduce_mean(self.G_loss_fir, name='G_loss_mean')
        tf.summary.scalar('G_loss_mean',loss_mean)
        
        
        #下面是原来有问题的loss函数，探究下为什么有问题
        self.test_ori_loss_G=-tf.reduce_mean( tf.log( tf.maximum(self.whole_net, incase_div_zero)  ))
        
        return loss_mean
    
    
    def trainonce_G(self,decay_steps=8000, decay_rate=0.99, beta1=beta1):
        #self.lr_rate = base_lr
        self.lr_rate = tf.train.exponential_decay(base_lr,  global_step=self.global_step, decay_steps=decay_steps, decay_rate=decay_rate)
        
        print ('G: AdamOptimizer to maxmize %d vars..'%(len(self.G_para)))
        
        #这将lr调为负数，因为应该最大化目标
        with tf.control_dependencies(tf.get_collection(tf.GraphKeys.UPDATE_OPS)):
            self.G_optimizer=tf.train.AdamOptimizer(self.lr_rate  , beta1=beta1)
            
            #for i in optimizer.compute_gradients(self.G_loss_mean, var_list=self.G_para): print (i)
            
            train_op =self.G_optimizer.minimize(self.G_loss_mean, global_step=self.global_step,var_list=self.G_para)
        
        return train_op
    
    def trainonce_D(self,decay_steps=8000, decay_rate=0.99, beta1=beta1):
        #self.lr_rate = base_lr
        self.lr_rate = tf.train.exponential_decay(base_lr,  global_step=self.global_step, decay_steps=decay_steps, decay_rate=decay_rate)
        
        print ('D: AdamOptimizer to maxmize %d vars..'%(len(self.D_para)))
        
        #这将lr调为负数，因为应该最大化目标
        #这里就不管globalstep了，否则一次迭代会加2次
        with tf.control_dependencies(tf.get_collection(tf.GraphKeys.UPDATE_OPS)):
            self.D_optimizer= tf.train.AdamOptimizer(self.lr_rate  , beta1=beta1)
            train_op=self.D_optimizer.minimize(self.D_loss_mean, var_list=self.D_para)   #global_step=self.global_step,
            train_op_real=self.D_optimizer.minimize(self.D_real_loss_mean, var_list=self.D_para) 
            train_op_fake=self.D_optimizer.minimize(self.D_fake_loss_mean, var_list=self.D_para) 
        return train_op,train_op_real,train_op_fake
                                                                                                                                                       
    
    
    
    #tensor 范围外   !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
    def train_once_all(self):
        #print ('deb1',self.sess.run(self.debug))                   
        
        #debug2 d_fir  debug:g_last
        
        noise=self.get_noise()
        '''
        #train d first
        train_prob_t,debugout2,debugout1,lrr, deb_D, _,_,dloss=self.sess.run([self.D_net,
                                                                                self.debug2, self.debug, 
                                                                                self.lr_rate, 
                                                                                self.test_ori_loss_D , #测试自己的loss函数
                                                                                self.train_D_real, self.train_D_fake, self.D_loss_mean], 
                                                                                         feed_dict={  self.noise_pla: noise , self.training:True})
        '''
        #train d first
        train_prob_t,debugout2,debugout1,lrr, deb_D, _,dloss=self.sess.run([self.D_net,
                                                                                self.debug2, self.debug, 
                                                                                self.lr_rate, 
                                                                                self.test_ori_loss_D , #测试自己的loss函数
                                                                                self.train_D, self.D_loss_mean], 
                                                                                         feed_dict={  self.noise_pla: noise , self.training:True})
        
        print ('trained D:')
        print('D_first kernel[0,0,:,0]:\n',debugout2)
        print ('G_last kernel[0,0,:,0]:\n',debugout1)
        
        train_prob_f,debugout2,debugout1,deb_G, _,gloss,summary=self.sess.run([self.whole_net,
                                                                                self.debug2, self.debug,                                                 
                                                                                self.test_ori_loss_G, 
                                                                                self.train_G, self.G_loss_mean,
                                                                                self.summary_all], 
                                                                                     feed_dict={  self.noise_pla: noise , self.training:True})
        
        print ('trained G:')
        print('D_first kernel[0,0,:,0]:\n',debugout2,debugout2-self.deb_kep)
        self.deb_kep=debugout2
        print ('G_last kernel[0,0,:,0]:\n',debugout1,debugout1-self.deb_kep2)
        self.deb_kep2=debugout1
        
        '''
        #原版训练，有问题
        train_prob_f,train_prob_t,debugout2,debugout1,lrr, deb_D,deb_G, _,_,dloss,gloss,summary=self.sess.run([self.whole_net,self.D_net,
                                                                                self.debug2, self.debug, 
                                                                                self.lr_rate, 
                                                                                self.test_ori_loss_D ,self.test_ori_loss_G, 
                                                            self.train_D, self.train_G, self.D_loss_mean,self.G_loss_mean,
                                                            self.summary_all], 
                                                           feed_dict={  self.noise_pla: noise , self.training:True})
        '''
        
        
        print ('the lr_rate is:', lrr)
        print ('this train probs:', 'true:',np.mean(train_prob_t), '   false:',np.mean(train_prob_f))
        #print ('MyGloss:',deb_G, '  MyDloss:',deb_D)

        return summary,dloss,gloss
    
    def mybatchnorm(self, data, scope):
        return tf.contrib.layers.batch_norm(data,
                                            center=True, #如果为True，有beta偏移量；如果为False，无beta偏移量
                                            decay=0.9,#衰减系数,即有一个moving_mean和一个当前batch的mean，更新moving_mean=moving_mean*decay+(1-decay)*mean
                                            #合适的衰减系数值接近1.0,特别是含多个9的值：0.999,0.99,0.9。如果训练集表现很好而验证/测试集表现得不好，选择小的系数（推荐使用0.9）
                                            updates_collections=None,
                                            epsilon=1e-5, #防止除0
                                            scale=True, #如果为True，则乘以gamma。如果为False，gamma则不使用。当下一层是线性的时（例如nn.relu），由于缩放可以由下一层完成,可不要
                                            #reuse=tf.AUTO_REUSE,  #reuse的默认选项是None,此时会继承父scope的reuse标志
                                            #param_initializers=None, # beta, gamma, moving mean and moving variance的优化初始化
                                            #activation_fn=None, #用于激活，默认为线性激活函数
                                            #param_regularizers=None,# beta and gamma正则化优化
                                            #data_format=DATA_FORMAT_NHWC,
                                            is_training=self.training, # 图层是否处于训练模式。
                                            scope=scope)
    
    
    def tanh2img(self,tanhd):
        tep= (tanhd+1)*255//2
        return tep.astype(np.uint8)  
    
    
    def Run_G(self, training=False):
        noise=self.get_noise()
        inerimg, outerprob=self.sess.run([self.G_net, self.whole_net], feed_dict={self.noise_pla: noise, self.training:training})
        return inerimg, outerprob
    
    def Run_WholeNet(self, training=False):
        '''
        training 为false时，bn会用学习的参数bn，因此在训练时的prob和测试时的prob又很大差异
        '''
        noise=self.get_noise()
        probs=self.sess.run(self.whole_net, feed_dict={self.noise_pla: noise, self.training:training})
        return probs
    
    def Run_D(self, training=False):
          
        '''
        #这里imgs要求是tanh化过的，即归一化到-1~1 
        training 为false时，bn会用学习的参数bn，因此在训练时的prob和测试时的prob又很大差异
        ''' 
        probs=self.sess.run(self.D_net, feed_dict={self.training:training})  #, feed_dict={ self.imgs_pla: self.img2tanh(self.tf_inimg) })
        #越接近真实图像越接近1
        return probs
    
    
        
    def get_noise(self):
        return np.random.uniform(-1, 1, size=[batchsize, noise_size])
        #return np.random.random([batchsize, noise_size])
    
    def eval_G_once(self, step=0):
        desdir=op.join(logdir, str(step))
        if not op.isdir(desdir): os.makedirs(desdir)
        
        #这里cnt不应该大于batchsize(64)
        cnt=4
        
        #中间用cnt像素的黑色线分隔图片
        bigimg_len=img_size*cnt+(cnt-1)*cnt
        bigimg_bests=np.zeros([bigimg_len,bigimg_len,3], dtype=np.uint8)
        bigimg_name='step-'+str(step)+'_cnt-'+str(cnt)+'_batchsize-'+str(batchsize)+'.png'
        
        for i in range(cnt):
            tepimgs,probs=self.Run_G()
            #保存原图
            for ind,j in enumerate(tepimgs[:cnt*3]):  
                #print (j[0][0][0])
                j=self.tanh2img(j)      
                #print (j[0][0][0])        
                im = Image.fromarray(j)
                imgname=str(i)+'_'+str(ind)+".jpg"
                im.save(op.join(desdir, imgname))
            
            #每个batch选随机的cnt个合成图片
            #print (probs.shape)
            tep=list(range(batchsize))
            random.shuffle(tep) #随机取cnt个图
            tep=tep[:cnt]  #np.argsort(probs[:,0])[-cnt:]
            #print (tep)
            for ind,j in enumerate(tep):
                st_x= ind*(img_size+cnt) #列
                st_y= i*(img_size+cnt) #行
                bigimg_bests[st_y:st_y+img_size, st_x:st_x+img_size,:]=self.tanh2img(tepimgs[j])
        
        bigimg_dir=op.join(bigimgsdir, bigimg_name)
        im = Image.fromarray(bigimg_bests)
        im.save(bigimg_dir)
            
        print ('eval_G_once,saved imgs to:',desdir, '\nbestimgs to:',bigimg_dir)
        
    def evla_D_once(self,eval_step=eval_step):
        cnt_real=0
        cnt_fake=0
        for i in range(eval_step):
            probs=self.Run_WholeNet()
            #print ('show prob shape:',probs.shape)  #[32,1]
            cnt_fake+=np.mean(probs)
        
        for i in range(eval_step):
            probs=self.Run_D()
            cnt_real+=np.mean(probs)
        return cnt_real/eval_step, cnt_fake/eval_step
        
    
    def Generator_net(self, noise, withbias=False):
        first_channel=G_first_channel
        
        with tf.variable_scope('G_Generator_net',  reuse=tf.AUTO_REUSE) as scope: 
            # fc1
            with tf.variable_scope('G_fc1',  reuse=tf.AUTO_REUSE) as scope:                    
                G_fc1w = tf.get_variable('weights', [noise_size, 4*4*first_channel*8], dtype=tf.float32, initializer=tf.random_normal_initializer(stddev=self.stddev))
                self.G_fc1=tf.matmul(noise, G_fc1w)
                
                if withbias:
                    G_fc1b = tf.get_variable('bias', [4*4*first_channel*8], dtype=tf.float32, initializer=tf.constant_initializer(self.bias_init))
                    self.G_fc1 = tf.nn.bias_add(self.G_fc1, G_fc1b)
                    #show inner result
                    tf.summary.scalar('G_fir_bias_10',G_fc1b[10])
                
                #reshape
                self.G_fc1=tf.reshape(self.G_fc1, [-1, 4, 4, first_channel*8])
                
            ########################################################################################################################################
            #bn1 relu
            with tf.variable_scope('G_bn1',  reuse=tf.AUTO_REUSE) as scope: 
                #batchmorm
                self.G_fc1=self.mybatchnorm(self.G_fc1, scope)
            
                #relu
                #self.G_fc1 = tf.nn.leaky_relu(G_fc1l, self.leakyrelurate)
                self.G_fc1 = tf.nn.relu(self.G_fc1)
                
                #self.G_para += [G_fc1w, G_fc1b]
                
            #######################################################################################################################################    
            #dropout1
            #self.G_fc1=tf.cond(self.training, lambda: tf.nn.dropout(self.G_fc1, self.dropout), lambda: self.G_fc1)
            
            ##########################################################################################################################################
            #deconv1
            with tf.variable_scope('G_deconv1',  reuse=tf.AUTO_REUSE) as scope:  
                kernel=tf.get_variable('weights', [4,4, first_channel*4, first_channel*8], dtype=tf.float32, initializer=tf.random_normal_initializer(stddev=self.stddev))
                #tf.nn.conv2d中的filter参数，是[filter_height, filter_width, in_channels, out_channels]的形式，
                #而tf.nn.conv2d_transpose中的filter参数，是[filter_height, filter_width, out_channels，in_channels]的形式
                self.G_deconv1=tf.nn.conv2d_transpose(self.G_fc1, kernel, output_shape=[batchsize, 8, 8, first_channel*4], strides=[1,2,2,1], padding="SAME")
                
                if withbias:
                    bias=tf.get_variable('bias', [first_channel*4], dtype=tf.float32, initializer=tf.constant_initializer(self.bias_init))
                    self.G_deconv1=tf.nn.bias_add(self.G_deconv1, bias)
                
                #self.G_para += [kernel, bias]
                
            #############################################################################################################################################
            #bn2 relu
            with tf.variable_scope('G_bn2',  reuse=tf.AUTO_REUSE) as scope: 
                #batchmorm
                self.G_deconv1=self.mybatchnorm(self.G_deconv1, scope)
            
                #relu
                #self.G_deconv1 = tf.nn.leaky_relu(self.G_deconv1, self.leakyrelurate)
                self.G_deconv1 = tf.nn.relu(self.G_deconv1)
                
            
            #############################################################################################################################################
            self.G_conv1=self.G_deconv1
            '''
            #conv1
            with tf.variable_scope('G_conv1',  reuse=tf.AUTO_REUSE) as scope: 
                kernel=tf.get_variable('weights', [4,4, 128, 128], dtype=tf.float32, initializer=tf.random_normal_initializer(stddev=self.stddev))
                bias=tf.get_variable('bias', [128], dtype=tf.float32, initializer=tf.constant_initializer(self.bias_init))
                
                conv=tf.nn.conv2d(self.G_deconv1, kernel, strides=[1,1,1,1], padding='SAME')
                self.G_conv1=tf.nn.bias_add(conv, bias)
                
                self.G_para += [kernel, bias]
                
                #batchmorm
                self.G_conv1=tf.contrib.layers.batch_norm(self.G_conv1,
                                            decay=0.9,
                                            updates_collections=None,
                                            epsilon=1e-5,
                                            scale=True,
                                            reuse=tf.AUTO_REUSE,
                                            is_training=self.training,
                                            scope=scope)
            #reakyrelu1
                #self.G_conv1=tf.nn.leaky_relu(self.G_conv1, self.leakyrelurate)
                self.G_conv1=tf.nn.relu(self.G_conv1)
            '''
            
            ##############################################################################################################################################
            #deconv2
            with tf.variable_scope('G_deconv2',  reuse=tf.AUTO_REUSE) as scope:  
                kernel=tf.get_variable('weights', [4,4, first_channel*2, first_channel*4], dtype=tf.float32, initializer=tf.random_normal_initializer(stddev=self.stddev))
                #tf.nn.conv2d中的filter参数，是[filter_height, filter_width, in_channels, out_channels]的形式，
                #而tf.nn.conv2d_transpose中的filter参数，是[filter_height, filter_width, out_channels，in_channels]的形式
                self.G_deconv2=tf.nn.conv2d_transpose(self.G_conv1, kernel, output_shape=[batchsize, 16, 16, first_channel*2], strides=[1,2,2,1], padding="SAME")
                
                if withbias:
                    bias=tf.get_variable('bias', [first_channel*2], dtype=tf.float32, initializer=tf.constant_initializer(self.bias_init))
                    self.G_deconv2=tf.nn.bias_add(self.G_deconv2, bias)
                
                #self.G_para += [kernel, bias]
                
            ############################################################################################################################################
            #bn3 relu
            with tf.variable_scope('G_bn3',  reuse=tf.AUTO_REUSE) as scope: 
                #batchmorm
                self.G_deconv2=self.mybatchnorm(self.G_deconv2, scope)
                
                #relu
                #self.G_deconv2=tf.nn.leaky_relu(self.G_deconv2, self.leakyrelurate)
                self.G_deconv2=tf.nn.relu(self.G_deconv2)
            
            ##############################################################################################################################################
            self.G_conv2=self.G_deconv2
            '''
            #conv2
            with tf.variable_scope('G_conv2',  reuse=tf.AUTO_REUSE) as scope: 
                kernel=tf.get_variable('weights', [4,4, 128, 64], dtype=tf.float32, initializer=tf.random_normal_initializer(stddev=self.stddev))
                bias=tf.get_variable('bias', [64], dtype=tf.float32, initializer=tf.constant_initializer(self.bias_init))
                
                conv=tf.nn.conv2d(self.G_deconv2, kernel, strides=[1,1,1,1], padding='SAME')
                self.G_conv2=tf.nn.bias_add(conv, bias)
                
                self.G_para += [kernel, bias]
                
                #batchmorm
                self.G_conv2=tf.contrib.layers.batch_norm(self.G_conv2,
                                            decay=0.9,
                                            updates_collections=None,
                                            epsilon=1e-5,
                                            scale=True,
                                            reuse=tf.AUTO_REUSE,
                                            is_training=self.training,
                                            scope=scope)
            #reakyrelu2
                #self.G_conv2=tf.nn.leaky_relu(self.G_conv2, self.leakyrelurate)
                self.G_conv2=tf.nn.relu(self.G_conv2)
            '''
            
            ###########################################################################################################################################
            #deconv3
            with tf.variable_scope('G_deconv3',  reuse=tf.AUTO_REUSE) as scope:  
                kernel=tf.get_variable('weights', [4,4, first_channel, first_channel*2], dtype=tf.float32, initializer=tf.random_normal_initializer(stddev=self.stddev))
                #tf.nn.conv2d中的filter参数，是[filter_height, filter_width, in_channels, out_channels]的形式，
                #而tf.nn.conv2d_transpose中的filter参数，是[filter_height, filter_width, out_channels，in_channels]的形式
                self.G_deconv3=tf.nn.conv2d_transpose(self.G_conv2, kernel, output_shape=[batchsize, 32, 32, first_channel], strides=[1,2,2,1], padding="SAME")
                
                if withbias:
                    bias=tf.get_variable('bias', [first_channel], dtype=tf.float32, initializer=tf.constant_initializer(self.bias_init))
                    self.G_deconv3=tf.nn.bias_add(self.G_deconv3, bias)
                
                #self.G_para += [kernel, bias]
            
            ############################################################################################################################################
            #bn4 relu
            with tf.variable_scope('G_bn4',  reuse=tf.AUTO_REUSE) as scope: 
                #batchmorm
                self.G_deconv3=self.mybatchnorm(self.G_deconv3, scope)
                
                #relu
                #self.G_deconv3=tf.nn.leaky_relu(self.G_deconv3, self.leakyrelurate)
                self.G_deconv3=tf.nn.relu(self.G_deconv3)
            
            ########################################################################################################################################
            self.G_conv3=self.G_deconv3
            '''
            #conv3
            with tf.variable_scope('G_conv3',  reuse=tf.AUTO_REUSE) as scope: 
                kernel=tf.get_variable('weights', [4,4, 64, 3], dtype=tf.float32, initializer=tf.random_normal_initializer(stddev=self.stddev))
                bias=tf.get_variable('bias', [3], dtype=tf.float32, initializer=tf.constant_initializer(self.bias_init))
                
                conv=tf.nn.conv2d(self.G_conv2, kernel, strides=[1,1,1,1], padding='SAME')
                self.G_conv3=tf.nn.bias_add(conv, bias)
                
                self.G_para += [kernel, bias]
                #self.G_conv3=tf.nn.leaky_relu(self.G_conv3, self.leakyrelurate)
                self.debug=bias
                tf.summary.scalar('G_last_bias[0]',bias[2])
            '''
            
            ############################################################################################################################################
            #deconv4
            with tf.variable_scope('G_deconv4',  reuse=tf.AUTO_REUSE) as scope:  
                kernel=tf.get_variable('weights', [5,5, 3, first_channel], dtype=tf.float32, initializer=tf.random_normal_initializer(stddev=self.stddev))
                #tf.nn.conv2d中的filter参数，是[filter_height, filter_width, in_channels, out_channels]的形式，
                #而tf.nn.conv2d_transpose中的filter参数，是[filter_height, filter_width, out_channels，in_channels]的形式
                self.G_deconv4=tf.nn.conv2d_transpose(self.G_conv3, kernel, output_shape=[batchsize, 96, 96, 3], strides=[1,3,3,1], padding="SAME")
                
                if withbias:
                    bias=tf.get_variable('bias', [3], dtype=tf.float32, initializer=tf.constant_initializer(self.bias_init))               
                    self.G_deconv4=tf.nn.bias_add(self.G_deconv4, bias)
                    
                self.debug=kernel[0,0,:,0]
                #self.G_para += [kernel, bias]
                
            '''   
            #############################################################################################################################################
            #bn5
            with tf.variable_scope('G_bn5',  reuse=tf.AUTO_REUSE) as scope: 
                #batchmorm
                self.G_deconv4=self.mybatchnorm(self.G_deconv4, scope)
                
                #self.G_deconv2=tf.nn.leaky_relu(self.G_deconv2, self.leakyrelurate)
                
                #self.G_deconv4=tf.nn.relu(self.G_deconv4)
            
            '''    
            #####################################################################################################################################
            #tanh
            self.G_tanh= tf.nn.tanh(self.G_deconv4, name='G_tanh')
        
        return self.G_tanh
            
                
    
    def Discriminator_net(self, imgs, withbias=False):
        #这里输入的imgs应该是tanh后的，位于-1~1之间
        #cast to float 
        self.imgs_float32=tf.cast(imgs, tf.float32)
        
        first_d_channel=D_first_channel
        with tf.variable_scope('D_Discriminator_net',  reuse=tf.AUTO_REUSE) as scope:
            #conv1
            with tf.variable_scope('D_conv1',  reuse=tf.AUTO_REUSE) as scope: 
                kernel=tf.get_variable('weights', [5,5, 3, first_d_channel], dtype=tf.float32, initializer=tf.random_normal_initializer(stddev=self.stddev))
                self.D_conv1=tf.nn.conv2d(self.imgs_float32, kernel, strides=[1,3,3,1], padding='SAME')
                #tf.nn.conv2d中的filter参数，是[filter_height, filter_width, in_channels, out_channels]的形式，
                #而tf.nn.conv2d_transpose中的filter参数，是[filter_height, filter_width, out_channels，in_channels]的形式
                #self.deb1=kernel
                
                if withbias:
                    bias=tf.get_variable('bias', [first_d_channel], dtype=tf.float32, initializer=tf.constant_initializer(self.bias_init))
                    self.D_conv1=tf.nn.bias_add(self.D_conv1, bias)
                    tf.summary.scalar('D_fir_bias_20',bias[20])
                #self.D_para += [kernel, bias]
                
            #######################################################################################################################
            self.debug2=kernel[0,0,:,0]
                            
        
            ###############################################################################################################################
            #bn1 lrelu
            with tf.variable_scope('D_bn1',  reuse=tf.AUTO_REUSE) as scope: 
                #batchmorm
                #self.D_conv1=self.mybatchnorm(self.D_conv1, scope)
                #leaky relu1
                self.D_conv1=tf.nn.leaky_relu(self.D_conv1, self.leakyrelurate)
                
            #############################################################################################################################
            #conv2
            with tf.variable_scope('D_conv2',  reuse=tf.AUTO_REUSE) as scope: 
                kernel=tf.get_variable('weights', [4,4, first_d_channel, first_d_channel*2], dtype=tf.float32, initializer=tf.random_normal_initializer(stddev=self.stddev))
                #tf.nn.conv2d中的filter参数，是[filter_height, filter_width, in_channels, out_channels]的形式，
                #而tf.nn.conv2d_transpose中的filter参数，是[filter_height, filter_width, out_channels，in_channels]的形式
                self.D_conv2=tf.nn.conv2d(self.D_conv1, kernel, strides=[1,2,2,1], padding='SAME')
                
                if withbias:
                    bias=tf.get_variable('bias', [first_d_channel*2], dtype=tf.float32, initializer=tf.constant_initializer(self.bias_init))
                    self.D_conv2=tf.nn.bias_add(self.D_conv2, bias)
                
                #self.D_para += [kernel, bias]
                
            ################################################################################################################################
            #bn2 lrelu
            with tf.variable_scope('D_bn2',  reuse=tf.AUTO_REUSE) as scope: 
                #batchmorm
                self.D_conv2=self.mybatchnorm(self.D_conv2, scope)
                self.D_conv2=tf.nn.leaky_relu(self.D_conv2, self.leakyrelurate)
                
            ################################################################################################################################
            #conv3
            with tf.variable_scope('D_conv3',  reuse=tf.AUTO_REUSE) as scope: 
                kernel=tf.get_variable('weights', [4,4, first_d_channel*2, first_d_channel*4], dtype=tf.float32, initializer=tf.random_normal_initializer(stddev=self.stddev))
                #tf.nn.conv2d中的filter参数，是[filter_height, filter_width, in_channels, out_channels]的形式，
                #而tf.nn.conv2d_transpose中的filter参数，是[filter_height, filter_width, out_channels，in_channels]的形式
                self.D_conv3=tf.nn.conv2d(self.D_conv2, kernel, strides=[1,2,2,1], padding='SAME')
                
                if withbias:
                    bias=tf.get_variable('bias', [first_d_channel*4], dtype=tf.float32, initializer=tf.constant_initializer(self.bias_init))
                    self.D_conv3=tf.nn.bias_add(self.D_conv3, bias)
                
                #self.D_para += [kernel, bias]
            
            ################################################################################################################################
            #bn3 lrelu
            with tf.variable_scope('D_bn3',  reuse=tf.AUTO_REUSE) as scope: 
                #batchmorm
                self.D_conv3=self.mybatchnorm(self.D_conv3, scope)
                self.D_conv3=tf.nn.leaky_relu(self.D_conv3, self.leakyrelurate)
                
            ##############################################################################################################################
            #conv4
            with tf.variable_scope('D_conv4',  reuse=tf.AUTO_REUSE) as scope: 
                kernel=tf.get_variable('weights', [4,4, first_d_channel*4, first_d_channel*8], dtype=tf.float32, initializer=tf.random_normal_initializer(stddev=self.stddev))
                #tf.nn.conv2d中的filter参数，是[filter_height, filter_width, in_channels, out_channels]的形式，
                #而tf.nn.conv2d_transpose中的filter参数，是[filter_height, filter_width, out_channels，in_channels]的形式
                self.D_conv4=tf.nn.conv2d(self.D_conv3, kernel, strides=[1,2,2,1], padding='SAME')
                
                if withbias:
                    bias=tf.get_variable('bias', [first_d_channel*8], dtype=tf.float32, initializer=tf.constant_initializer(self.bias_init))
                    self.D_conv4=tf.nn.bias_add(self.D_conv4, bias)
                
                #self.D_para += [kernel, bias]
                
            ###############################################################################################################################
            #bn4
            with tf.variable_scope('D_bn4',  reuse=tf.AUTO_REUSE) as scope: 
                #batchmorm
                self.D_conv4=self.mybatchnorm(self.D_conv4, scope)
                self.D_conv4=tf.nn.leaky_relu(self.D_conv4, self.leakyrelurate)
                
                #print ('tensor to last cnn:',self.D_conv4)
                #self.D_conv4 :  Tensor("D_conv4/LeakyRelu:0", shape=(64, 4, 4, 768), dtype=float32)
                
            ##################################################################################################################################
            '''
            #flatten
            self.flatten=tf.reshape(self.D_conv4, [batchsize, -1])
            
            # fc1
            with tf.variable_scope('D_fc1',  reuse=tf.AUTO_REUSE) as scope:                    
                D_fc1w = tf.get_variable('weights', [self.flatten.get_shape()[-1], 1024], dtype=tf.float32, initializer=tf.random_normal_initializer(stddev=self.stddev))
                D_fc1b = tf.get_variable('bias', [1024], dtype=tf.float32, initializer=tf.constant_initializer(self.bias_init))
            
                self.D_fc1 = tf.nn.bias_add(tf.matmul(self.flatten, D_fc1w), D_fc1b)
                
                
                self.D_para += [D_fc1w, D_fc1b]
                
                #batchmorm
                self.D_fc1=tf.contrib.layers.batch_norm(self.D_fc1,
                                            decay=0.9,
                                            updates_collections=None,
                                            epsilon=1e-5,
                                            scale=True,
                                            reuse=tf.AUTO_REUSE,
                                            is_training=self.training,
                                            scope=scope)
                
                self.D_fc1 = tf.nn.leaky_relu(self.D_fc1, self.leakyrelurate)
            
            #fc2
            with tf.variable_scope('D_fc2',  reuse=tf.AUTO_REUSE) as scope:                    
                D_fc2w = tf.get_variable('weights', [1024, 1], dtype=tf.float32, initializer=tf.random_normal_initializer(stddev=self.stddev))
                D_fc2b = tf.get_variable('bias', [1], dtype=tf.float32, initializer=tf.constant_initializer(self.bias_init))
            
                self.D_fc2 = tf.nn.bias_add(tf.matmul(self.D_fc1, D_fc2w), D_fc2b)
                
                self.D_para += [D_fc2w, D_fc2b]
            '''    
            
            ##################################################################################################################################
            #conv5
            with tf.variable_scope('D_conv5',  reuse=tf.AUTO_REUSE) as scope: 
                kernel=tf.get_variable('weights', [4,4, first_d_channel*8, 1], dtype=tf.float32, initializer=tf.random_normal_initializer(stddev=self.stddev))
                #tf.nn.conv2d中的filter参数，是[filter_height, filter_width, in_channels, out_channels]的形式，
                #而tf.nn.conv2d_transpose中的filter参数，是[filter_height, filter_width, out_channels，in_channels]的形式
                self.D_conv5=tf.nn.conv2d(self.D_conv4, kernel, strides=[1,1,1,1], padding='VALID')
                
                if withbias:
                    bias=tf.get_variable('bias', [1], dtype=tf.float32, initializer=tf.constant_initializer(self.bias_init))                
                    self.D_conv5=tf.nn.bias_add(self.D_conv5, bias) #Tensor("D_Discriminator_net/D_conv5/BiasAdd:0", shape=(64, 1, 1, 1), dtype=float32)
                    tf.summary.scalar('D_last_bias',bias[0])
                #self.D_para += [kernel, bias]
                
                #这里最好将self.D_conv5由4维转为2维[batchsize,]
                self.D_conv5=self.D_conv5[:,:,0,0]  #shape=(64,1)
                #print ('self.D_conv5 ',self.D_conv5)
            
            #######################################################################################################################################
            #sigmoid
            self.D_sigmoid=tf.nn.sigmoid(self.D_conv5, name='D_sigmoid')
            
        return self.D_sigmoid,self.D_conv5
        
        




if __name__ == '__main__':   
    with tf.Session() as sess:      
        gan=GAN_Net(sess)
        
        logwriter = tf.summary.FileWriter(logdir,   sess.graph)
        
        all_saver = tf.train.Saver(max_to_keep=2) 


        begin_t=time.time()
        for i in range(maxstep):            
            if ((i+1)%500==0):#一次测试
                print ('\nbegining to eval D:')
                real,fake=gan.evla_D_once()
                print ('mean prob of real/fake:',real,fake)
                
                #自己构建summary
                tsummary = tf.Summary()
                tsummary.value.add(tag='mean prob of real', simple_value=real)
                tsummary.value.add(tag='mean prob of fake', simple_value=fake)
                #tsummary.value.add(tag='test epoch loss:', simple_value=tloss)
                #写入日志
                logwriter.add_summary(tsummary, i)
                
            if i==0 or (i+1)%1000==0:#保存一波图片
                gan.eval_G_once(i)
                
                
            if (i+1)%2000==0:#保存模型
                print ('saving models...')
                pat=all_saver.save(sess, op.join(logdir,'model_keep'),global_step=i)
                print ('saved at:',pat)
            
            
            stt=time.time()
            print ('\n%d/%d  start train_once...'%(i,maxstep))
            #lost,sum_log=vgg.train_once(sess) #这里每次训练都run一个summary出来
            sum_log,dloss,gloss=gan.train_once_all()
            #写入日志
            logwriter.add_summary(sum_log, i)
            #print ('write summary done!')
            
            #######################
            
            real,fake=gan.evla_D_once(1)
            print ('once prob of real/fake:',real,fake)
            
            print ('train once-->gloss:',gloss,'  dloss:',dloss)
            
            print ('time used:',time.time()-stt,' to be ',1.0/(time.time()-stt),' iters/s', ' left time:',(time.time()-stt)*(maxstep-i)/60/60,' hours')
            
        
        print ('Training done!!!-->time used:',(time.time()-begin_t),'s = ',(time.time()-begin_t)/60,' min')








