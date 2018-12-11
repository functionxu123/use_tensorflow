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
import use_tensor.GAN_HW_LEEHONGYI.HW3_1_gen_anime_tfrecord as anime_data


#!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!

TIMESTAMP = "{0:%Y-%m-%d_%H-%M-%S}".format(datetime.now())


train_size=33431 #训练集规模
batchsize=32
noise_size=100
img_size=64  #96

base_lr=0.00002 #基础学习率
beta=0.5

maxstep=100000 #训练多少次
eval_step=1000

decay_steps=1000
decay_rate=0.9

logdir="./logs/GAN_"+TIMESTAMP+('_base_lr-%f_batchsize-%d_maxstep-%d'%(base_lr,batchsize, maxstep))
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
        self.stddev=0.1
        self.bias_init=0
        
        #3个placeholder， img和noise,training 
        self.noise_pla=tf.placeholder(tf.float64, [batchsize, noise_size], name='noise_in')
        self.imgs_pla = tf.placeholder(tf.float64, [batchsize, img_size, img_size, 3], name='imgs_in')
        self.training=tf.placeholder(tf.bool, name='training_in')
        
        for i in self.G_para: print (i)
        for i in self.D_para: print (i)
        
        self.whole_net=self.Discriminator_net(self.Generator_net(self.noise_pla))
        self.D_net=self.Discriminator_net(  self.img2tanh(self.tf_inimg)  ) #self.imgs_pla
        self.G_net=self.Generator_net(self.noise_pla)
        self.D_loss_mean=self.D_loss()
        self.G_loss_mean=self.G_loss()
        self.train_D=self.trainonce_D(decay_steps, decay_rate)
        self.train_G=self.trainonce_G(decay_steps, decay_rate)
        
        self.summary_all=tf.summary.merge_all()
        init = tf.global_variables_initializer()#初始化tf.Variable,虽然后面会有初始化权重过程，但是最后一层是要根据任务来的,无法finetune，其参数需要随机初始化
        self.sess.run(init)
        
        
    def img2tanh(self,img):
        return img*2/255-1
    
            
    def D_loss(self):
        fir=tf.log(self.D_net)
        sec=tf.log(self.whole_net*(-1)+1)
        loss=tf.add_n([fir,sec] )
        #print ('loss shape:',loss.get_shape())
        loss_mean = tf.reduce_mean(loss, name='D_loss_mean')
        
        tf.summary.scalar('D_loss_mean',loss_mean)
        
        return loss_mean
        
    
    def G_loss(self):
        sec=tf.log(self.whole_net)
        loss_mean = tf.reduce_mean(sec, name='G_loss_mean')
        tf.summary.scalar('G_loss_mean',loss_mean)
        
        return loss_mean
    
    
    def trainonce_G(self,decay_steps=1000, decay_rate=0.99):
        lr_rate = tf.train.exponential_decay(base_lr,  global_step=self.global_step, decay_steps=decay_steps, decay_rate=decay_rate)
        print ('G: AdamOptimizer to maxmize %d vars..'%(len(self.G_para)))
        
        #这将lr调为负数，因为应该最大化目标
        train_op = tf.train.AdamOptimizer(-lr_rate).minimize(self.G_loss_mean, global_step=self.global_step,var_list=self.G_para)
        
        return train_op
    
    def trainonce_D(self,decay_steps=1000, decay_rate=0.99):
        lr_rate = tf.train.exponential_decay(base_lr,  global_step=self.global_step, decay_steps=decay_steps, decay_rate=decay_rate)
        print ('D: AdamOptimizer to maxmize %d vars..'%(len(self.D_para)))
        
        #这将lr调为负数，因为应该最大化目标
        #这里就不管globalstep了，否则一次迭代会加2次
        train_op = tf.train.AdamOptimizer(-lr_rate).minimize(self.D_loss_mean, var_list=self.D_para)   #global_step=self.global_step,
        
        return train_op
                                                                                                                                                       
    
    
    
    #tensor 范围外   !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
    def train_once_all(self):
        noise=self.get_noise()
        _,dloss=self.sess.run([self.train_D, self.D_loss_mean], feed_dict={  self.noise_pla: noise })  #self.imgs_pla: self.img2tanh(self.tf_inimg),
        
        noise=self.get_noise()
        _,summary,gloss=self.sess.run([self.train_G, self.summary_all, self.G_loss_mean], feed_dict={  self.noise_pla: noise })   #self.imgs_pla: self.img2tanh(self.tf_inimg),
        return summary,dloss,gloss
    
    
    def tanh2img(self,tanhd):
        tep= (tanhd+1)*255//2
        return tep.astype(np.uint8)  
    
    
    def Run_G(self):
        noise=self.get_noise()
        inerimg=self.sess.run(self.G_net, feed_dict={self.noise_pla: noise})
        return inerimg
    
    def Run_WholeNet(self):
        noise=self.get_noise()
        probs=self.sess.run(self.whole_net, feed_dict={self.noise_pla: noise})
        return probs
    
    def Run_D(self):#这里imgs要求是tanh化过的，即归一化到-1~1       
        probs=self.sess.run(self.D_net)  #, feed_dict={ self.imgs_pla: self.img2tanh(self.tf_inimg) })
        #越接近真实图像越接近1
        return probs
    
    
        
    def get_noise(self):
        return np.random.random([batchsize, noise_size])
    
    def eval_G_once(self, step=0):
        desdir=op.join(logdir, str(step))
        if not op.isdir(desdir): os.makedirs(desdir)
        
        for i in range(10):
            tepimgs=self.Run_G()
            for ind,j in enumerate(tepimgs):  
                j=self.tanh2img(j)              
                im = Image.fromarray(j)
                imgname=str(i)+'_'+str(ind)+".jpg"
                im.save(op.join(desdir, imgname))
        print ('eval_G_once,saved imgs to:',desdir)
        
    def evla_D_once(self):
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
        
    
    def Generator_net(self, noise):
        # fc1
        with tf.variable_scope('G_fc1',  reuse=tf.AUTO_REUSE) as scope:                    
            G_fc1w = tf.get_variable('weights', [noise_size, 128*16*16], dtype=tf.float64, initializer=tf.random_normal_initializer(stddev=self.stddev))
            G_fc1b = tf.get_variable('bias', [128*16*16], dtype=tf.float64, initializer=tf.constant_initializer(self.bias_init))
        
            G_fc1l = tf.nn.bias_add(tf.matmul(noise, G_fc1w), G_fc1b)
            
            self.G_fc1 = tf.nn.leaky_relu(G_fc1l, self.leakyrelurate)
            self.G_para += [G_fc1w, G_fc1b]
        
        #dropout1
        #self.G_fc1=tf.cond(self.training, lambda: tf.nn.dropout(self.G_fc1, self.dropout), lambda: self.G_fc1)
        
        #reshape
        self.G_fc1=tf.reshape(self.G_fc1, [-1, 16,16,128])
        
        #deconv1
        with tf.variable_scope('G_deconv1',  reuse=tf.AUTO_REUSE) as scope:  
            kernel=tf.get_variable('weights', [3,3, 128, 128], dtype=tf.float64, initializer=tf.random_normal_initializer(stddev=self.stddev))
            bias=tf.get_variable('bias', [128], dtype=tf.float64, initializer=tf.constant_initializer(self.bias_init))
            #tf.nn.conv2d中的filter参数，是[filter_height, filter_width, in_channels, out_channels]的形式，
            #而tf.nn.conv2d_transpose中的filter参数，是[filter_height, filter_width, out_channels，in_channels]的形式
            deconv=tf.nn.conv2d_transpose(self.G_fc1, kernel, output_shape=[batchsize, 32, 32, 128], strides=[1,2,2,1], padding="SAME")
            self.G_deconv1=tf.nn.bias_add(deconv, bias)
            
            self.G_para += [kernel, bias]
            #self.G_deconv1=tf.nn.leaky_relu(self.G_deconv1, self.leakyrelurate)
            
        #conv1
        with tf.variable_scope('G_conv1',  reuse=tf.AUTO_REUSE) as scope: 
            kernel=tf.get_variable('weights', [4,4, 128, 128], dtype=tf.float64, initializer=tf.random_normal_initializer(stddev=self.stddev))
            bias=tf.get_variable('bias', [128], dtype=tf.float64, initializer=tf.constant_initializer(self.bias_init))
            
            conv=tf.nn.conv2d(self.G_deconv1, kernel, strides=[1,1,1,1], padding='SAME')
            self.G_conv1=tf.nn.bias_add(conv, bias)
            
            self.G_para += [kernel, bias]
            self.G_conv1=tf.nn.leaky_relu(self.G_conv1, self.leakyrelurate)
            
        #deconv2
        with tf.variable_scope('G_deconv2',  reuse=tf.AUTO_REUSE) as scope:  
            kernel=tf.get_variable('weights', [3,3, 64, 128], dtype=tf.float64, initializer=tf.random_normal_initializer(stddev=self.stddev))
            bias=tf.get_variable('bias', [64], dtype=tf.float64, initializer=tf.constant_initializer(self.bias_init))
            #tf.nn.conv2d中的filter参数，是[filter_height, filter_width, in_channels, out_channels]的形式，
            #而tf.nn.conv2d_transpose中的filter参数，是[filter_height, filter_width, out_channels，in_channels]的形式
            deconv=tf.nn.conv2d_transpose(self.G_conv1, kernel, output_shape=[batchsize, 64, 64, 64], strides=[1,2,2,1], padding="SAME")
            self.G_deconv2=tf.nn.bias_add(deconv, bias)
            
            self.G_para += [kernel, bias]
            #self.G_deconv2=tf.nn.leaky_relu(self.G_deconv2, self.leakyrelurate)
            
        #conv2
        with tf.variable_scope('G_conv2',  reuse=tf.AUTO_REUSE) as scope: 
            kernel=tf.get_variable('weights', [4,4, 64, 64], dtype=tf.float64, initializer=tf.random_normal_initializer(stddev=self.stddev))
            bias=tf.get_variable('bias', [64], dtype=tf.float64, initializer=tf.constant_initializer(self.bias_init))
            
            conv=tf.nn.conv2d(self.G_deconv2, kernel, strides=[1,1,1,1], padding='SAME')
            self.G_conv2=tf.nn.bias_add(conv, bias)
            
            self.G_para += [kernel, bias]
            self.G_conv2=tf.nn.leaky_relu(self.G_conv2, self.leakyrelurate)
            
        #conv3
        with tf.variable_scope('G_conv3',  reuse=tf.AUTO_REUSE) as scope: 
            kernel=tf.get_variable('weights', [4,4, 64, 3], dtype=tf.float64, initializer=tf.random_normal_initializer(stddev=self.stddev))
            bias=tf.get_variable('bias', [3], dtype=tf.float64, initializer=tf.constant_initializer(self.bias_init))
            
            conv=tf.nn.conv2d(self.G_conv2, kernel, strides=[1,1,1,1], padding='SAME')
            self.G_conv3=tf.nn.bias_add(conv, bias)
            
            self.G_para += [kernel, bias]
            #self.G_conv3=tf.nn.leaky_relu(self.G_conv3, self.leakyrelurate)
            
        #tanh
        self.G_tanh= tf.nn.tanh(self.G_conv3, name='G_tanh')
        
        return self.G_tanh
            
                
    
    def Discriminator_net(self, imgs):
        imgs=tf.cast(imgs, tf.float64)
        #conv1
        with tf.variable_scope('D_conv1',  reuse=tf.AUTO_REUSE) as scope: 
            kernel=tf.get_variable('weights', [4,4, 3, 32], dtype=tf.float64, initializer=tf.random_normal_initializer(stddev=self.stddev))
            bias=tf.get_variable('bias', [32], dtype=tf.float64, initializer=tf.constant_initializer(self.bias_init))
            #tf.nn.conv2d中的filter参数，是[filter_height, filter_width, in_channels, out_channels]的形式，
            #而tf.nn.conv2d_transpose中的filter参数，是[filter_height, filter_width, out_channels，in_channels]的形式
            conv=tf.nn.conv2d(imgs, kernel, strides=[1,2,2,1], padding='SAME')
            self.D_conv1=tf.nn.bias_add(conv, bias)
            
            self.D_para += [kernel, bias]
            self.D_conv1=tf.nn.leaky_relu(self.D_conv1, self.leakyrelurate)
            
        #conv2
        with tf.variable_scope('D_conv2',  reuse=tf.AUTO_REUSE) as scope: 
            kernel=tf.get_variable('weights', [4,4, 32, 64], dtype=tf.float64, initializer=tf.random_normal_initializer(stddev=self.stddev))
            bias=tf.get_variable('bias', [64], dtype=tf.float64, initializer=tf.constant_initializer(self.bias_init))
            #tf.nn.conv2d中的filter参数，是[filter_height, filter_width, in_channels, out_channels]的形式，
            #而tf.nn.conv2d_transpose中的filter参数，是[filter_height, filter_width, out_channels，in_channels]的形式
            conv=tf.nn.conv2d(self.D_conv1, kernel, strides=[1,2,2,1], padding='SAME')
            self.D_conv2=tf.nn.bias_add(conv, bias)
            
            self.D_para += [kernel, bias]
            self.D_conv2=tf.nn.leaky_relu(self.D_conv2, self.leakyrelurate)
            
        #conv3
        with tf.variable_scope('D_conv3',  reuse=tf.AUTO_REUSE) as scope: 
            kernel=tf.get_variable('weights', [4,4, 64, 128], dtype=tf.float64, initializer=tf.random_normal_initializer(stddev=self.stddev))
            bias=tf.get_variable('bias', [128], dtype=tf.float64, initializer=tf.constant_initializer(self.bias_init))
            #tf.nn.conv2d中的filter参数，是[filter_height, filter_width, in_channels, out_channels]的形式，
            #而tf.nn.conv2d_transpose中的filter参数，是[filter_height, filter_width, out_channels，in_channels]的形式
            conv=tf.nn.conv2d(self.D_conv2, kernel, strides=[1,2,2,1], padding='SAME')
            self.D_conv3=tf.nn.bias_add(conv, bias)
            
            self.D_para += [kernel, bias]
            self.D_conv3=tf.nn.leaky_relu(self.D_conv3, self.leakyrelurate)
            
        #conv4
        with tf.variable_scope('D_conv4',  reuse=tf.AUTO_REUSE) as scope: 
            kernel=tf.get_variable('weights', [4,4, 128, 256], dtype=tf.float64, initializer=tf.random_normal_initializer(stddev=self.stddev))
            bias=tf.get_variable('bias', [256], dtype=tf.float64, initializer=tf.constant_initializer(self.bias_init))
            #tf.nn.conv2d中的filter参数，是[filter_height, filter_width, in_channels, out_channels]的形式，
            #而tf.nn.conv2d_transpose中的filter参数，是[filter_height, filter_width, out_channels，in_channels]的形式
            conv=tf.nn.conv2d(self.D_conv3, kernel, strides=[1,2,2,1], padding='SAME')
            self.D_conv4=tf.nn.bias_add(conv, bias)
            
            self.D_para += [kernel, bias]
            self.D_conv4=tf.nn.leaky_relu(self.D_conv4, self.leakyrelurate)
            
        #flatten
        self.flatten=tf.reshape(self.D_conv4, [batchsize, -1])
        
        # fc1
        with tf.variable_scope('D_fc1',  reuse=tf.AUTO_REUSE) as scope:                    
            D_fc1w = tf.get_variable('weights', [self.flatten.get_shape()[-1], 1], dtype=tf.float64, initializer=tf.random_normal_initializer(stddev=self.stddev))
            D_fc1b = tf.get_variable('bias', [1], dtype=tf.float64, initializer=tf.constant_initializer(self.bias_init))
        
            self.D_fc1 = tf.nn.bias_add(tf.matmul(self.flatten, D_fc1w), D_fc1b)
            
            #self.D_fc1 = tf.nn.leaky_relu(self.D_fc1, self.leakyrelurate)
            self.D_para += [D_fc1w, D_fc1b]
            
        #sigmoid
        self.D_sigmoid=tf.nn.sigmoid(self.D_fc1, name='D_sigmoid')
        
        return self.D_sigmoid
        
        




if __name__ == '__main__':   
    with tf.Session() as sess:      
        gan=GAN_Net(sess)
        
        logwriter = tf.summary.FileWriter(logdir,   sess.graph)
        
        all_saver = tf.train.Saver(max_to_keep=2) 


        begin_t=time.time()
        for i in range(maxstep):            
            if (i==0 or (i+1)%500==0):#一次测试
                gan.eval_G_once(i)
                
                print ('begining to eval D:')
                real,fake=gan.evla_D_once()
                print ('mean prob of real/fake:',real,fake)
                
                #自己构建summary
                tsummary = tf.Summary()
                tsummary.value.add(tag='mean prob of real', simple_value=real)
                tsummary.value.add(tag='mean prob of fake', simple_value=fake)
                #tsummary.value.add(tag='test epoch loss:', simple_value=tloss)
                #写入日志
                logwriter.add_summary(tsummary, i)
                
                
                
            if (i+1)%2000==0:#保存模型
                print ('saving models...')
                pat=all_saver.save(sess, op.join(logdir,'model_keep'),global_step=i)
                print ('saved at:',pat)
            
            
            stt=time.time()
            print ('\n%d/%d  start train_once...'%(i,maxstep))
            #lost,sum_log=vgg.train_once(sess) #这里每次训练都run一个summary出来
            sum_log,gloss,dloss=gan.train_once_all()
            #写入日志
            logwriter.add_summary(sum_log, i)
            #print ('write summary done!')
            
            print ('train once-->gloss:',gloss,'  dloss:',dloss,'  time:',time.time()-stt)
        
        print ('Training done!!!-->time used:',(time.time()-begin_t))








